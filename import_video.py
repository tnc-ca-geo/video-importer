import argparse
import time
import shelve
import imp
import json
import psutil
import os
import sys
import hashlib
import datetime
import csv
import StringIO
import re
import traceback
import logging
import requests

try:
    from hachoir_core import config
    from hachoir_parser import createParser
    from hachoir_metadata import extractMetadata
    HAVE_HACHOIR = True
except:
    HAVE_HACHOIR = False

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

re_notascii = re.compile('\W')

def get_duration(filename):
    duration = None
    try:
        if HAVE_HACHOIR:
            filename = unicode(filename, "utf-8")
            parser = createParser(filename)
            metadata = extractMetadata(parser, quality=1.0)
            duration = metadata.getValues('duration')[0].total_seconds()
        return duration
    except:
        logging.error("error while getting duration meta-data from movie (%s)", filename)
        logging.error(traceback.format_exc())
        return None

class GenericImporter(object):
    
    def get_params(self, path):
        camera = epoch = lat = lng = None
        if self.regex:
            match = self.regex.match(path)
            if match:
                try:
                    camera_name = match.group('camera')
                    logging.info('camera_name: %s', camera)
                except: pass
                try:
                    epoch = int(match.group('epoch'))
                    logging.info('epoch: %s', epoch)
                except: pass
                try:
                    lat = float(match.group('lat'))                    
                except: pass
                try:
                    lng = float(match.group('lng'))
                except: pass
        if not camera_name:
            logging.error('did not detect camera name, assuming "%s"', self.DEFAULT_CAMERA_NAME)
            sys.exit(1)
        if not epoch:
            epoch = os.path.getctime(path)        
            logging.warn('did not detect epoch, assuming "%s" (time file was last changed)', epoch)
        timestamp = datetime.datetime.fromtimestamp(epoch).isoformat()
        # in case the epoch does nt have milliseconds
        if len(timestamp)==19: timestamp = timestamp+'.000'
        return {'camera':camera_name, 'timestamp':timestamp, 'lat':lat, 'lng':lng}

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
        found_new = False
        job_id = None
        for filename in self.folder_walker(path):        
            params = self.get_params(filename)
            key = self.hashfile(filename)
            given_name = params['camera']+'.'+params['timestamp']+'.'+key+'.mp4'
            if key in scheduled:
                logging.info('%s (duplicate)' % filename)
            elif key in db and db[key]['uploaded_on'] is not None:
                logging.info('%s (uploaded)' % filename)
            else:
                logging.info('%s (scheduled for upload)' % filename)
                found_new = True # if we reach this point we found a new file
                self.cameras[params['camera']] = None
                scheduled.add(key)
                if key in db:
                    params = db[key]
                else:
                    params['filename'] = filename
                    params['duration'] = get_duration(filename) or 0
                    params['key'] = key
                    params['given_name'] = given_name
                    params['discovered_on'] = discovered_on
                    params['uploaded_on'] = None
                    params['confirmed_on'] = None
                    params['job_id'] = None
                    params['shard_id'] = None
                    params['size'] = os.path.getsize(params['filename'])
                    db[key] = params
                    db.sync()
                unprocessed.append(params)
                if not params.get('job_id'):
                    unscheduled.append(params)

        if not found_new:
            logging.info("no new files found to upload, exiting..")
            sys.exit(0)

        for camera_name in self.cameras:
            camera_config = self.register_camera(camera_name)
            camera_id = camera_config.get('camera_id')
            if not camera_id:
                logging.error("unable to properly register camera with service (no unique camera ID returned)")
                #@TODO - what to do here? Keep going on a best-effort basis, fail fast and early?
            logging.debug("Camera ID: %r", camera_id)
            self.cameras[camera_name] = camera_config

        if hasattr(self.module, 'set_hook_data'):
            # now we know all of the camera configuration data, give it to the hook module in case they need it
            logging.debug("setting camera config data in hook module for cameras: %r", [name for name in self.cameras])
            self.module.set_hook_data(dict(registered_cameras=[self.cameras[name] for name in self.cameras]))

        # let the camera registration info prop. to Box and let Box kick off the webserver
        time.sleep(1)
        if hasattr(self.module, 'assign_job_ids'):
            job_id = self.assign_job_ids(db, unscheduled)

        total_count = len(unprocessed)
        jobs = set()
        for k, params in enumerate(unprocessed):
            logging.info('%i/%i uploading %s' % (k+1, total_count, params['filename']))
            if self.args.verbose:
                logging.info('input-file %s has been renamed %s', params['filename'], given_name)
            latlng = (params['lat'], params['lng'])
            logging.debug("Params: %r", params)
            success = self.post_video(params['camera'], params['timestamp'], params['filename'], latlng)
            if success:
                logging.info('completed')
            else:
                logging.error('unable to post')
                break
            params['uploaded_on'] = self.now()
            jobs.add((params['job_id'], params['shard_id']))
            db[params['key']] = params
            db.sync()

        if hasattr(self.module, 'register_jobs'):
            ret = self.register_jobs(db, jobs)
            if not ret:
                logging.error("not able to register jobs")
        db.close()
        return job_id

    def list_files(self, path):
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
        self.DEFAULT_CAMERA_NAME = 'unnamed' # used if we can't parse a camera name from video file names
        self.REQUIRED_MODULE_CALLBACK_FUNCTIONS = ['register_camera', 'post_video_content']
        self.DEFAULT_FILE_REGEX = ".*/(?P<camera>\w+?)\-.*\-(?P<epoch>\d+)\.mp4"

        self.parser = argparse.ArgumentParser()
        # optional arguments/flags
        self.parser.add_argument('-v', '--verbose', action='store_true', default=False, help='set logging level to debug')
        self.parser.add_argument('-q', '--quiet', action='store_true', default=False, help='set logging level to errors only')
        self.parser.add_argument('-c', '--csv', action='store_true', default=False, help='dump csv log file')
        self.parser.add_argument('-p', '--port', default='8080', help='the segmenter port number (default: 8080)')
        self.parser.add_argument('-r', '--regex', default=self.DEFAULT_FILE_REGEX, 
                help=('regex to extract input-file meta-data. The two capture group fields are <camera> and <epoch> '
                     'which capture the name of the camera that the video originates from and the timestamp of the start of '
                     'the video respectively. (default: "%s")' % self.DEFAULT_FILE_REGEX))
        self.parser.add_argument('-s', '--storage', default='.processes.shelve',
                            help='full path to the local storage db (default: ./.processes.shelve)')
        self.parser.add_argument('-d', '--hook_data_json', default=None,
                            help='a json object containing extra information to be passed to the hook-module')
        self.parser.add_argument('-f', '--hook_data_json_file', default=None,
                            help=('full path to a file containing a json object of extra info to be passed to the hook module.'
                            'note - the values passed in through this trump the same values passed in through the `-d` param'))

        # required, postitional arguments
        self.parser.add_argument('folder', help='full path to folder of input videos to process')
        self.parser.add_argument('hook_module', help='full path to hook module for custom functions (a python file)')
        self.parser.add_argument('host', help='the IP-address or hostname of the segmenter')
        self.define_custom_args()

    def init_args(self):
        self.args = self.parser.parse_args()
        if self.args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        elif self.args.quiet:
            logging.getLogger().setLevel(logging.ERROR)
        logging.info("submitted hooks module: %r", self.args.hook_module)
        self.module = imp.load_source('hooks_module', self.args.hook_module)
        # ensure all required callback functions exist
        for hook_callback in self.REQUIRED_MODULE_CALLBACK_FUNCTIONS:
            if not hasattr(self.module, hook_callback):
                logging.error("hooks-module (%s) is missing required function: %s", self.args.hook_module, hook_callback)
                logging.error("see README.md for information on required hook callback functions")
                sys.exit(1)
        if hasattr(self.module, 'set_hook_data'):
            hook_data = dict(logger=logging.getLogger())
            if self.args.hook_data_json:
                hook_data.update(json.loads(self.args.hook_data_json))
            if self.args.hook_data_json_file:
                if not os.path.exists(self.args.hook_data_json_file):
                    logging.error("--hook_data_json_file value: %s does not exist", self.args.hook_data_json_file)
                    sys.exit(1)
                try:
                    with open(self.args.hook_data_json_file) as fh:
                        data = json.loads(fh.read())
                except:
                    logging.error("error while loading json data from file: %s", self.args.hook_data_json_file)
                    logging.error("traceback:\n%r", traceback.format_exc())
                    sys.exit(1)
                hook_data.update(data)
            self.module.set_hook_data(hook_data)

    def run(self):
        self.init_args()
        if self.args.csv:
            logging.info(self.list_files(self.args.folder))
        else:
            return self.upload_folder(self.args.folder)

    def define_custom_args(self):
        """ 
        legacy stuff, doubt this will be used in the future. custom args are now
        passed into the hooks module via the `--hook_data_json` argument, where the json
        is deserialized and passed into the set_hook_data() function in the hooks module
        @TODO - remove this and the call to it when you're sure it isn't being used anymore
        """
        pass
        
    def register_camera(self, camera_name):
        host, port = self.args.host, self.args.port
        return self.module.register_camera(camera_name, host, port)

    def assign_job_ids(self, db, unscheduled):
        logging.debug("assigning job id: %r", unscheduled)
        if 'assign_job_ids' in dir(self.module):
            return self.module.assign_job_ids(self, db, unscheduled)
        return

    def register_jobs(self, db, jobs):
        logging.debug("registering jobs: %r", jobs)
        if 'register_jobs' in dir(self.module):
            return self.module.register_jobs(self, db, jobs)
        return

    def post_video(self, camera_name, timestamp, filepath, latlng):
        host, port = self.args.host, self.args.port
        camera_id = self.cameras[camera_name].get('camera_id')
        return self.module.post_video_content(host, port, camera_name, camera_id, filepath, timestamp, latlng)

def main():
    job_id = GenericImporter().run()
    logging.info("finishing up...")
    if job_id:
        logging.info("Job ID: %s", job_id)
    else:
        logging.warn("no Job ID found, did something go wrong?")

if __name__=='__main__':
    main()
