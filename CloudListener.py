import scratchattach as scratch3
import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# config variables
project_id = "1023022765"
chars = ["gnaw", "edward"]
max_len = 5

# firebase init
cred = credentials.Certificate("key.json")
firebase_admin.initialize_app(cred)
database = firestore.client()
db = database.collection('sfrt_scores')

data = {}
for char in chars:
    data[char] = db.document(char).get().to_dict()

#functions
def log(msg):
    #print(msg)
    file_name = 'logfile.txt'
    f = open(file_name, 'a+')
    f.write(f"[{datetime.datetime.now()}] {msg} \n")
    f.close()

def var_set(val, user):
    if (user is None):
        return

    score = int(val[2:2+(int(val[:2]) - 10)])
    char = char_str(val[-2:-1])
    diff = diff_str(val[-1:])

    if(char is None or diff is None):
        return
    chunk = data[char][diff]
    doc = None
    if(user in chunk):
        if(score > chunk[user]):
            log("new personal highscore - updating old entry")
            doc = {diff:{user:score}}
    else:
        if(len(chunk) < max_len):
            log("filling available space - adding new entry")
            doc = {diff:{user:score}}
        elif(chunk[min(chunk, key=chunk.get)] < score):
            log("delete worst entry and add new entry")
            doc = {diff:{min(chunk, key=chunk.get): firestore.DELETE_FIELD, user:score}}
    if(doc is None):
        log("nothing changed")
    else:
        db.document(char).set(doc, merge=True)

def char_str(nr):
    match nr:
        case "1":
            return "gnaw"
        case "5":
            return "edward"
        case _:
            log(f"ERROR: unknown character id: {nr}")
            return None

def diff_str(nr):
    match nr:
        case "1":
            return "beginner"
        case "3":
            return "experienced"
        case "5":
            return "insane"
        case _:
            log(f"ERROR: unknown difficulty id: {nr}")
            return None

#initialize cloud listeners to scratch.mit.edu and turbowarp.org
log("cloud listener initializing")
s_events = scratch3.CloudEvents(project_id)
last_timestamp = 0
#t_events = scratch3.TwCloudEvents(project_id, purpose="scratchrunning.com scoreboard", contact="sfrt.default552@passinbox.com")

@s_events.event
def on_set(event):
    global last_timestamp
    if(event.timestamp > last_timestamp):
        last_timestamp = event.timestamp
    else:
        log("old data - dismissed")
        return
    if (event.var == "CloudUpdate"):
        log(f"SCRATCH UPDATE - user: {event.user} - raw data: {event.value}")
        var_set(event.value, event.user)

@s_events.event
def on_ready():
   log("listening to scratch.mit.edu...")

""" @t_events.event
def on_set(event):
    if (event.var == "CloudUpdate"):
        log(f"TURBOWARP UPDATE - user: {event.user} - raw data: {event.value}")
        var_set(event.value, event.user)

@t_events.event
def on_ready():
   log("listening to turbowarp.org...") """

s_events.start()
#t_events.start()