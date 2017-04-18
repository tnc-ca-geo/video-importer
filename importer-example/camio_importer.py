#
# python importer.py -a {auth_token} -d {device_id} -u {user_id} -f {folder}
#
from importer import *

class CamioImporter(GenericImporter):

    def define_custom_args(self):
        self.parser.add_argument('-p', '--post_url', default='http://127.0.0.1:8888/upload/{filename}',
                                 help='URL to post')
        self.parser.add_argument('-S', '--server', default='https://test.camio.com',
                                 help='base url of the API service')
        self.parser.add_argument('-a', '--auth_token', default=None,
                                 help='auth token for header')
        self.parser.add_argument('-d', '--device_id', default=None,
                                 help='device_id')
        self.parser.add_argument('-u', '--user_id', default=None,
                                 help='user_id')
        
    def register_camera(self, camera_name):
        """
        This is an example in case the the service requires registration of the camera
        """
        print 'registering camera %s' % camera_name
        server, auth_token, user_id, device_id = self.args.server, self.args.auth_token, self.args.user_id, self.args.device_id
        url = server+'/api/cameras/discovered'
        local_camera_id = hashlib.sha1(camera_name).hexdigest()
        payload = {
            local_camera_id: {
                "device_id_discovering": device_id,
                "acquisition_method": "batch",
                "discovery_history": {},
                "device_user_agent": "CamioBox (Linux; virtualbox) Firmware:box-virtualbox-cam.unknown",
                "user_id": user_id,
                "local_camera_id": local_camera_id,
                "name": camera_name,
                "mac_address": local_camera_id,
                "is_authenticated": False,
                "should_config": False,
                }
            }
        headers = {'Authorization': 'token %s' % auth_token}
        try:
            res = requests.post(url, json=payload, headers=headers)
            res_data = res.json()
            assert local_camera_id in res_data
        except:
            print 'register camera "%s" error' % camera_name
            sys.exit(1)
        print 'registered "%s" => local_camera_id "%s"' % (camera_name, local_camera_id)
        return local_camera_id

    def assign_job_ids(self, db, unscheduled):
        item_count = len(unscheduled)
        # if we have files to upload follow process in https://github.com/CamioCam/Camiolog-Web/issues/4555
        if item_count:
            server, device_id, auth_token = self.args.server, self.args.device_id, self.args.auth_token
            item_average_size_bytes = sum(params['size'] for params in unscheduled)/item_count
            payload = {'device_id':device_id, 'item_count':item_count, 'item_average_size_bytes':item_average_size_bytes}
            headers = {'Authorization': 'token %s' % auth_token}
            res = requests.put(server+'/api/jobs', json=payload, headers=headers)         
            try:
                shards = res.json()
            except:
                print res.content
                print 'server response error: %r' % res
                sys.exit(1)
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

    def register_jobs(self, db, jobs):
        for job_id, shard_id in jobs:
            rows = filter(lambda params: (params['job_id'], params['shard_id']) == (job_id, shard_id), db.values())
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

    def post_video(self, camera, timestamp, key, filename):
        auth_token = self.args.auth_token
        camera_id = self.cameras[camera]
        vars = 'camera_id=%s&timestamp=%s,hash=%s,access_token=%s' % (camera_id, timestamp, key, auth_token)
        url = self.args.post_url+'?'+vars
        return self.upload_filename(filename, url)

if __name__=='__main__':
    CamioImporter().run()
