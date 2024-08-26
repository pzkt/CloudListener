import scratchattach as scratch3
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import logging
import sched, time
from logging.handlers import RotatingFileHandler

#logging
logger = logging.getLogger('')
logger.setLevel(logging.WARNING)
handler = RotatingFileHandler('logfile.log', maxBytes=1024*1024, backupCount=1)
logger.addHandler(handler)

# config variables
project_id = "1023501055"
chars = ["gnaw", "edward"]
max_len = 10

# firebase init
cred = credentials.Certificate("key.json")
firebase_admin.initialize_app(cred)
database = firestore.client()
db = database.collection('sfrt_scores')
metadata = database.collection('meta').document('sfrt')
metadata.set({'heartbeat':firestore.SERVER_TIMESTAMP}, merge=True)

data = {}
for char in chars:
    data[char] = db.document(char).get().to_dict()

#functions
def log(msg):
    logger.warning(f"[{datetime.datetime.now()}] {msg} \n")

def var_set(val, user):
    global data
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
        data[char] = db.document(char).get().to_dict()
        metadata.set({'last_update':firestore.SERVER_TIMESTAMP}, merge=True)

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
last_timestamp = 1716320516
#t_events = scratch3.TwCloudEvents(project_id, purpose="scratchrunning.com scoreboard", contact="sfrt.default552@passinbox.com")

@s_events.event
def on_set(event):
    global last_timestamp
    if(event.timestamp > last_timestamp):
        last_timestamp = event.timestamp
        metadata.set({'last_data':firestore.SERVER_TIMESTAMP}, merge=True)

    if (event.var == "CloudUpdate2"):
        log(f"SCRATCH UPDATE - user: {event.user} - raw data: {event.value} - timestamp: {event.timestamp}")
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

#signal that we are still alive
def heartbeat(scheduler): 
    scheduler.enter(600, 1, heartbeat, (scheduler,))
    log("sending heartbeat...")
    metadata.set({'heartbeat':firestore.SERVER_TIMESTAMP}, merge=True)

my_scheduler = sched.scheduler(time.time, time.sleep)
my_scheduler.enter(600, 1, heartbeat, (my_scheduler,))
my_scheduler.run()