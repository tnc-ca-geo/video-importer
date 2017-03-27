sudo apt-get install mongodb
sudo apt-get install python-dev
pip install bottle gunicorn pymongo requests
echo <<EOF >app.py
"""
This script installs and runs a sample web server that handles
requests for labeling. This python hook receives images and posts 
back the resulting labels to the requested callback_url.

This sample exposed only two urls:
1) POST /tasks/<API_KEY> - handles the payload of images to label.
2) GET /tasks - responds with the JSON description of all uploaded events pending processing.

All uploaded events are stored in the tasks collection in mongodb.
A background process extracts them from mongodb and posts the labels back to the callback_url.
"""
from __future__ import print_function
from bottle import route, run, request, response, default_app
import pymongo
import json
import requests
import time
import logging
import traceback

API_KEY = '123456789'

connection = pymongo.MongoClient()
db = connection['mydb']
tasks = db['tasks']

# a basic URL route to test whether Bottle is responding properly
@route('/')
def index():
    return "it works!"

@route('/tasks/<secret>',method='POST')
def post_task(secret):
    body = request.body.read()    
    logging.info('payload size %s' % len(body))
    if secret != API_KEY:
        response.status = 400
        return "Invalid API Key"
    if body:
        payload = json.loads(body.decode('utf8'))
        tasks.insert({'request': payload, 'status':'pending'})
        logging.info('done')
        images = payload.get('images')
    return 'ok'

@route('/tasks',method='GET')
def get_tasks():
    all_tasks = tasks.find({'status':'pending'})
    return repr([task['request']['user_id']+'/'+task['request']['camera'] for task in all_tasks])

###########################################################################
# This is the function that you modify to perform your particular labeling.
# The payload images looks like:
# {
#   ...
# }
#
###########################################################################
def compute_labels(images):
    return ['cat','dog','mouse']

def runtasks():
    t = 0
    while True:
        task = tasks.find_one({'status':'pending'})
        if task:
            t = 0
            print('processing task')
            request = task['request']
            try:
                images = request['images']
                callback_url = request['callback_url']
                labels = compute_labels(images)
                payload = {'status':'success', 'labels':labels}
                print('    posting payload')
                requests.post(callback_url, json=payload)
                print('    done!')
                task['status'] = 'completed'
            except:
                task['status'] = 'error'
                task['traceback'] = traceback.format_exc()
            tasks.update({'_id':task['_id']}, task)
        else:
            print('... %i ...' % t)
            t += 10
            time.sleep(10)

# these two lines are only used for python app.py
if __name__ == '__main__':
    runtasks()
    
# this is the hook for Gunicorn to run Bottle
app = default_app()
EOF
nohup gunicorn -w 2 app:app -b 0.0.0.0 > /tmp/gunicorn.log &
nohup python app.py > /tmp/taskqueue.log &
