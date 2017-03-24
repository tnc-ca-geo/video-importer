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

import requests

re_notascii = re.compile('\W')

def get_params(path, regex=None):    
    camera = epoch = None
    if regex:
        match = regex.match(path)
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
    if  len(timestamp)==19: timestamp = timestamp+'.000'
    return {'camera':camera, 'timestamp':timestamp}

def now():
    return datetime.datetime.now().isoformat()

def folder_walker(path, extensions=['.mp4']):
    for root, subpaths, filenames in os.walk(path):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                fullpath = os.path.join(root,filename)
                yield fullpath

def lock_or_exit(lock_filename, message="process %s is already running"):
    pid = psutil.Process().pid
    if os.path.exists(lock_filename):
        with open(lock_filename) as lockfile:            
            old_pid = int(lockfile.read())
            if old_pid in psutil.pids():
                print message % old_pid
                sys.exit(1)
            else:
                os.unlink(lock_filename)

def hashfile(filename):
    hasher = hashlib.sha1()
    with open(filename) as myfile:
        for chunk in iter(lambda: myfile.read(4096), ''):
            hasher.update(chunk)
    return hasher.hexdigest()

def upload_filename(filename, url, verbose): 
    headers = {}  
    # todo: maybe some try ... except
    with open(filename, 'rb') as myfile:
        try:
            res = requests.post(url, headers=headers, data=myfile)
            return res.response_status == 200
        except:
            print 'connection refused'
            return False

def upload_folder(path, dbname='.processes.shelve', post_url=None, 
                  regex=None, verbose=False, auth_token=None):
    if regex:
        regex = re.compile(regex)
    shelve_name = os.path.join(os.path.dirname(__file__),dbname)
    shelve_name_lock = shelve_name + '.lock'
    lock_or_exit(shelve_name_lock)
    db = shelve.open(shelve_name)
    unprocessed = []
    scheduled = set()
    for filename in folder_walker(path):        
        params = get_params(filename, regex)
        key = hashfile(filename)
        given_name = params['camera']+'.'+params['timestamp']+'.'+key+'.mp4'
        if key in scheduled:
            print '%s (duplicate)' % filename
        elif key in db and db[key]['uploaded_on']:
            print '%s (uploaded)' % filename
        else:
            print '%s (scheduled for upload)' % filename
            scheduled.add(key)
            params['filename'] = filename
            params['key'] = key
            params['given_name'] = given_name
            unprocessed.append(params)

    k_max = len(unprocessed)
    for k, params in enumerate(unprocessed):
        print '%i/%i uploading %s' % (k+1, k_max, params['filename'])
        if verbose:
            print '     renamed %s' % given_name
        discovered_on = now()
        params['discovered_on'] = now()
        params['uploaded_on'] = None
        db[key] = params
        if post_url:
            vars = 'camera_id=%s&timestamp=%s,hash=%s,access_token=%s' % (
                params['camera'], params['timestamp'], key, auth_token)
            url = post_url+'?'+vars
            success = upload_filename(filename, url, verbose)
            if success:
                print 'completed'
            else:
                print 'error'
                break
        params['uploaded_on'] = now()
        db[key] = params
        db.sync()
    db.close()

def listfiles(path, dbname='.processes.shelve'):    
    shelve_name = os.path.join(os.path.dirname(__file__),dbname)
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
    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--post_url', default='http://127.0.0.1:8888/upload/{filename}',
                        help='URL to post')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='log more info')
    parser.add_argument('-r', '--regex', default='(?P<camera>.*?)/.*',
                        help='regex to find camera name')
    parser.add_argument('-c', '--csv', action='store_true', default=False,
                        help='dump csv log file')
    parser.add_argument('-s', '--storage', default='.processes.shelve',
                        help='location of the local storage db')
    parser.add_argument('-f', '--folder', default='data',
                        help='folder to process')
    parser.add_argument('-a', '--auth_token', default=None,
                        help='auth token for header')
    args = parser.parse_args()

    if args.csv:
        print listfiles(args.folder, dbname=args.storage)
    else:
        upload_folder(args.folder, dbname=args.storage, post_url=args.post_url, 
                      regex=args.regex, verbose=args.verbose, auth_token=args.auth_token)

if __name__=='__main__':
    main()
