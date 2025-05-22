import scratchattach as scratch3
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
import time
import math
import logging
import requests
import sched, time
from logging.handlers import RotatingFileHandler
from pprint import pprint

#logging
logger = logging.getLogger('')
logger.setLevel(logging.WARNING)
handler = RotatingFileHandler('logfile.log', maxBytes=1024*1024, backupCount=1)
logger.addHandler(handler)

# config variables
chars = ["arc","co-op","ed","gnaw","phantom","xavier"]
project_id = "184411641"
max_len = 20

# firebase init
cred = credentials.Certificate("key.json")
firebase_admin.initialize_app(cred)
database = firestore.client()
sfrt_db = database.collection('sfrt_scores_v2')
metadata = database.collection('meta').document('sfrt')
recent_db = sfrt_db.document('recent')

# --- reset boards ---
""" def reset_boards():
    for c in chars:
        sfrt_db.document(c).set({"0":{},"1":{},"2":{}})
reset_boards()
exit() """
# --------------------

# update local information
userdata = sfrt_db.document('userdata').get().to_dict()

data = {}
for c in chars:
    data[c] = sfrt_db.document(c).get().to_dict()

#functions
def log(msg):
    logger.warning(f"[{datetime.now()}] {msg} \n")
    print(msg)

#number to character string converter
def char_str(nr):
    match nr:
        case "01":
            return "gnaw"
        case "02":
            return "phantom"
        case "03":
            return "arc"
        case "04":
            return "xavier"
        case "05":
            return "ed"
        case _:
            log(f"ERROR: unknown character id: {nr}")
            return None

#called when a score is recorded. val is the raw data
def var_set(val, user):
    if(len(val) < 11):
        log(f"ERROR: value too short")
        return
    #version number control
    if(val[:2] != "02"):
        log(f"ERROR: wrong version number: {val[:2]}")
        return
    #get chars
    chars = []
    chars.append(char_str(val[6:8]))
    if(val[8:10] != "00"):
        print(val[8:10])
        chars.append(char_str(val[8:10]))

    diff = val[5]
    score = int(val[10:])

    #msg validation
    if(None in chars):
        return
    if(diff not in ["0","1","2"]):
        log(f"ERROR: invalid difficulty: {diff}")
        return
    if(score < 1):
        log("WARNING: zero score")
        return
    log(f"decoded: user: {user}, chars: {chars}, diff: {diff}, score: {score}")
    add_score(user, chars, diff, score)

#add a username-id key-value pair to firestore for pfps and add to cumulative score
def add_user_data(user, score):
    if(user not in userdata):
        response = requests.get(f"https://api.scratch.mit.edu/users/{user}").json()

        if(not response.ok):
            return
        try:
            res = response.json()
        except ValueError:
            return

        if("id" not in res):
            return
        userdata[user] = {}
        userdata[user]["id"] = res["id"]
        userdata[user]["score"] = score
    else:
        userdata[user]["score"] += score
    sfrt_db.document('userdata').set(userdata)

def add_score(user, chars, diff, score):
    #add to recent scores
    new_entry = {"user": user, "chars": chars, "diff": diff, "score": score, "time": datetime.now(timezone.utc)}
    recent_doc = recent_db.get()
    recents = recent_doc.to_dict().get("scores", [])
    recents_sorted = sorted(recents, key=lambda x: x.get('time'), reverse=True)[:max_len]
    recent_db.set({'scores' : [new_entry] + recents_sorted[:max_len-1]})

    #calc cumulative scores and ids for users 
    add_user_data(user, score)

    #check if score needs to be added to top scores and add it
    mode = "co-op" if len(chars) != 1 else chars[0]

    #add score to darc counter
    if(mode != "co-op"):
        sfrt_db.document('darc_goals').update({mode: firestore.Increment(score)})
    else:
        sfrt_db.document('darc_goals').update({chars[0]: firestore.Increment(score // 2)})
        sfrt_db.document('darc_goals').update({chars[1]: firestore.Increment(score // 2)})

    #data[mode] = sfrt_db.document(mode).get().to_dict() #enable to get local storage resilience

    chunk = data[mode][diff]
    change = False
    if(user in chunk):
        if(score > chunk[user]["score"]):
            log("new personal highscore - updating old entry")
            change = True
    else:
        if(len(chunk) < max_len):
            log("filling available space - adding new entry")
            change = True
        elif(min([e["score"] for e in chunk.values()]) < score):
            log("delete worst entry and add new entry")
            min_score = min(chunk[k]['score'] for k in chunk)
            worst_keys = [k for k in chunk if chunk[k]['score'] == min_score]
            worst_key = min(worst_keys, key=lambda k: chunk[k]['time'])
            del data[mode][diff][worst_key]
            change = True
    if(not change):
        log("nothing changed")
    else:
        data[mode][diff][user] = {"score": score, "time": datetime.now(timezone.utc)}
        if(mode == "co-op"):
            data[mode][diff][user]["chars"] = chars;
        sfrt_db.document(mode).set(data[mode])

# --- manually add entry ---
""" add_score("scratchcat",["xavier"],"0",0)
#var_set("020102010264", "test")
exit() """
# --------------------------

#initialize cloud listeners to scratch.mit.edu and turbowarp.org
log("cloud listener initializing")
cloud = scratch3.get_scratch_cloud(project_id)
s_events = cloud.events()
last_timestamp = math.floor(time.time()*1000)

@s_events.event
def on_set(event):
    global last_timestamp
    if(event.timestamp > last_timestamp):
        last_timestamp = event.timestamp
        metadata.set({'last_data':firestore.SERVER_TIMESTAMP}, merge=True)
        if (event.var == "☁ CloudUpdate2"):
            log(f"SCRATCH UPDATE - user: {event.user} - raw data: {event.value} - timestamp: {event.timestamp}")
            var_set(event.value, event.user)
    else:
        log("old value")

@s_events.event
def on_ready():
   log("listening to scratch.mit.edu...")

#we don't do turbowarp for now
"""
@t_events.event
def on_set(event):
    if (event.var == "CloudUpdate"):
        log(f"TURBOWARP UPDATE - user: {event.user} - raw data: {event.value}")
        var_set(event.value, event.user)

@t_events.event
def on_ready():
   log("listening to turbowarp.org...")
"""

s_events.start()
#t_events.start()

#signal that we are still alive
def heartbeat(scheduler): 
    scheduler.enter(600, 1, heartbeat, (scheduler,))
    log("sending heartbeat...")
    metadata.set({'heartbeat':firestore.SERVER_TIMESTAMP}, merge=True)

my_scheduler = sched.scheduler(time.time, time.sleep)
my_scheduler.enter(600, 1, heartbeat, (my_scheduler,))
my_scheduler.run()
