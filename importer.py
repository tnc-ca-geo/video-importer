import argparse
import shelve
import psutil
import os
import sys
import hashlib
import datetime
import csv
import StringIO
import re
import logging

import requests

re_notascii = re.compile('\W')

class GenericImporter(object):
    
    def get_params(self, path):
        camera = epoch = None
        if self.regex:
            match = self.regex.match(path)
            if match:
                try:
                    camera = match.group('camera')
                except: pass
                try:
                    epoch = int(match.group('epoch'))
                except: pass
        
        if not camera:
            camera = "default"
        if not epoch:
            epoch = os.path.getctime(path)        
        timestamp = datetime.datetime.fromtimestamp(epoch).isoformat()
        # in case the epoch does nt have milliseconds
        if len(timestamp)==19: timestamp = timestamp+'.000'
        return {'camera':camera, 'timestamp':timestamp}

    def now(self):
        return datetime.datetime.now().isoformat()

    def folder_walker(self, path, extensions=['.mp4']):
        for root, subpaths, filenames in os.walk(path):
            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    fullpath = os.path.join(root,filename)
                    yield fullpath

    def lock_or_exit(self, lock_filename, message="process %s is already running"):
        pid = psutil.Process().pid
        if os.path.exists(lock_filename):
            with open(lock_filename) as lockfile:            
                old_pid = int(lockfile.read())
                if old_pid in psutil.pids():
                    logging.info(message % old_pid)
                    sys.exit(1)
                else:
                    os.unlink(lock_filename)

    def hashfile(self, filename):
        hasher = hashlib.sha1()
        with open(filename) as myfile:
            for chunk in iter(lambda: myfile.read(4096), ''):
                hasher.update(chunk)
                return hasher.hexdigest()

    def upload_filename(self, filename, url, headers=None): 
        headers = headers or {}  
        with open(filename, 'rb') as myfile:
            try:
                res = requests.post(url, headers=headers, data=myfile)
                return res.response_status == 200
            except:
                logging.error('connection refused')
                return False

    def upload_folder(self, path):
        self.regex = self.args.regex and re.compile(self.args.regex)
        shelve_name = os.path.join(os.path.dirname(__file__), self.args.storage)
        shelve_name_lock = shelve_name + '.lock'
        self.lock_or_exit(shelve_name_lock)
        db = shelve.open(shelve_name)
        self.cameras = {}
        unprocessed = []
        unscheduled = []
        scheduled = set()
        discovered_on = self.now()
        for filename in self.folder_walker(path):        
            params = self.get_params(filename)
            key = self.hashfile(filename)
            given_name = params['camera']+'.'+params['timestamp']+'.'+key+'.mp4'
            if key in scheduled:
                logging.info('%s (duplicate)' % filename)
            elif key in db and db[key]['uploaded_on']:
                logging.info('%s (uploaded)' % filename)
            else:
                logging.info('%s (scheduled for upload)' % filename)
                self.cameras[params['camera']] = None
                scheduled.add(key)
                if key in db:
                    params = db[key]
                else:
                    params['filename'] = filename
                    params['key'] = key
                    params['given_name'] = given_name
                    params['discovered_on'] = discovered_on
                    params['uploaded_on'] = None
                    params['confirmed_on'] = None
                    params['size'] = os.path.getsize(params['filename'])
                    db[key] = params
                    db.sync()
                unprocessed.append(params)
                if not params.get('job_id'):
                    unscheduled.append(params)

        for camera_name in self.cameras:
            camera_id = self.register_camera(camera_name)
            self.cameras[camera_name] = camera_id

        self.assign_job_ids(db, unscheduled)

        total_count = len(unprocessed)
        jobs = set()
        for k, params in enumerate(unprocessed):
            logging.info('%i/%i uploading %s' % (k+1, total_count, params['filename']))
            if self.args.verbose:
                logging.info('     renamed %s' % given_name)
            success = self.post_video(params['camera'], params['timestamp'], params['key'], params['filename'])
            if success:
                logging.info('completed')
            else:
                logging.error('unable to post')
                break
            params['uploaded_on'] = self.now()
            jobs.add((params['job_id'], params['shard_id']))
            db[key] = params
            db.sync()

        self.register_jobs(db, jobs)
        db.close()

    def listfiles(self, path):
        storage = self.args.storage
        shelve_name = os.path.join(os.path.dirname(__file__), storage)
        db = shelve.open(shelve_name)
        status = []
        for key, value in db.items():
            value['hash'] = key
            status.append(value)
            status.sort(lambda a,b: cmp(a['filename'],b['filename']))
        stream = StringIO.StringIO()
        writer = csv.writer(stream)
        writer.writerow(('FILENAME','GIVEN_NAME','CREATED_ON','DISCOVERED_ON','UPLOADED_ON'))
        for params in status:
            writer.writerow((params['filename'], params['given_name'],params['camera'],
                             params['timestamp'], params['discovered_on'], params['uploaded_on']))
        return stream.getvalue()
    
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('-v', '--verbose', action='store_true', default=False,
                            help='log more info')
        self.parser.add_argument('-r', '--regex', default='.*/(?P<camera>.+?)/(?P<epoch>\d+(.\d+)?).*',
                            help='regex to find camera name')
        self.parser.add_argument('-c', '--csv', action='store_true', default=False,
                            help='dump csv log file')
        self.parser.add_argument('-s', '--storage', default='.processes.shelve',
                            help='location of the local storage db')
        self.parser.add_argument('-f', '--folder', default='data',
                            help='folder to process')
        self.define_custom_args()

    def run(self):
        self.args = self.parser.parse_args()
        if self.args.csv:
            print self.listfiles(self.args.folder)
        else:
            self.upload_folder(self.args.folder)

    def define_custom_args(self):
        pass
        
    def register_camera(self, camera_name):
        return '000000000'

    def assign_job_ids(self, db, unscheduled):
        return

    def register_jobs(self, db, jobs):
        return

    def post_video(self, camera, timestamp, key, filename):
        logging.info('posting video %s for camera=%s @ %s' % (filename, camera, timestamp))
        return

if __name__=='__main__':
    GenericImporter().run()
