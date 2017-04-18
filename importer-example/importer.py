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
    with open(filename, 'rb') as myfile:
        try:
            res = requests.post(url, headers=headers, data=myfile)
            return res.response_status == 200
        except:
            print 'connection refused'
            return False

def register_camera(camera_name, device_id, server=None):
    """
    This is an example in case the the service requires registration of the camera
    """
    if server:
        url = server+'/api/cameras/discovered'
        local_camera_id = hashlib.sha1(camera_name).hexdigest()
        cameras = {local_camera_id: {'camera_name':camera_name}}
        payload = {'device_id':device_id, 'cameras':cameras}
        res = requests.post(url, json=payload)
        camera_id = res['cameras'][local_camera_id]['camera_id']
    else:
        camera_id = camera_name
    return camera_id

def upload_folder(path, dbname='.processes.shelve', post_url=None, auth_token=None,
                  regex=None, verbose=False, server=None, device_id=None):
    if regex:
        regex = re.compile(regex)
    shelve_name = os.path.join(os.path.dirname(__file__),dbname)
    shelve_name_lock = shelve_name + '.lock'
    lock_or_exit(shelve_name_lock)
    db = shelve.open(shelve_name)
    cameras = {}
    unprocessed = []
    unscheduled = []
    scheduled = set()
    discovered_on = now()
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
            cameras[params['camera']] = None
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

    if device_id:
        for camera in cameras:
            local_camera_id = register_camera(camera, device_id, server)
            cameras[camera] = local_camera_id

    item_count = len(unscheduled)
    # if we have files to upload follow process in https://github.com/CamioCam/Camiolog-Web/issues/4555
    if item_count and server:
        item_average_size_bytes = sum(params['size'] for params in unscheduled)/item_count
        payload = {'device_id':auth_token, 'item_count':item_count, 'item_average_size_bytes':item_average_size_bytes}
        res = requests.put(server+'/api/jobs', json=payload)         
        shards = res.json()
        job_id = shards['job_id']
        n = 0
        upload_urls = []
        for shard_id in sorted(shards['shard_map']):
            shard = shards['shard_map'][shard_id]
            n += shard['item_count']
            upload_urls.append((n, shard_id, shard['upload_url']))

        # for each new file to upload store the job_id and the upload_url from the proper shard
        upload_urls_k = 0
        for k, params in enumerate(unscheduled):        
            key = params['key']
            params['job_id'] = job_id
            while k>=upload_urls[upload_urls_k][0]: upload_urls_k += 1
            params['shard_id'] = upload_urls[upload_urls_k][1]
            params['upload_url'] = upload_urls[upload_urls_k][2]
            db[key] = params
            db.sync()

    total_count = len(unprocessed)
    jobs = set()
    for k, params in enumerate(unprocessed):
        print '%i/%i uploading %s' % (k+1, total_count, params['filename'])
        if verbose:
            print '     renamed %s' % given_name
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
        jobs.add((params['job_id'], params['shard_id']))
        db[key] = params
        db.sync()

    if server:
        for job_id, shard_id in jobs:
            rows = filter(lambda params: params['job_id'], params['shard_id'] == job_id, shard_id, db.values())
            hash_map = {}
            for params in rows:
                hash_map[params['key']] = {'original_filename': params['filename'], 'size_MB': params['size']/1e6}
                payload = {
                    'job_id': job_id,
                    'shard_id': shard_id,
                    'item_count':len(rows),
                    'hash_map': hash_map
                    }
            url = rows[0]['upload_url']
            requests.put(url, json=payload)

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
    parser.add_argument('-S', '--server', default='https://example.com',
                        help='base url of the API service')
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
    parser.add_argument('-d', '--device_id', default=None,
                        help='device_id')
    args = parser.parse_args()

    if args.csv:
        print listfiles(args.folder, dbname=args.storage)
    else:
        upload_folder(args.folder, dbname=args.storage, post_url=args.post_url,
                      regex=args.regex, verbose=args.verbose, auth_token=args.auth_token, server=args.server,
                      device_id=args.device_id)

if __name__=='__main__':
    main()
