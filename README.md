## video-importer
Traverses directories to import video as segmented events with correct timestamps and metadata. Details can be found [here](https://docs.google.com/document/d/1NoluaMS6brmOC9INlg2Ah9K9xM-aQcsoa-fe3x9WxDs/edit#)

### What is it
The importer is an Open Source project to automate the ingestion of video files so that they can be labeled by advanced classifiers
running either locally or in the cloud.

### Who is it for
The Importer is for all Electronic Monitoring (EM) services that record video for fisheries observation to report scientific and
regulatory data quickly.

### Why is it needed
The review and labeling of recorded video is slow. In fact, the elapsed time to review is often longer than the fishing trip's duration.
Until boats at-sea have the compute power and bandwidth sufficient to analyze, extract and upload data in real-time, the video review must
start with the on-shore processing of hard drives filled with recorded video. 

The importer makes it fast and simple to create labeled video bookmarks automatically so that the EM's own review tools and processes can
jump to the relevant video segments rather than wade through hours of video. For example, the reviewer can jump directly to events in
which tuna or marlin was brought on board as in [this demo](https://www.youtube.com/watch?v=0BUWRHd_jss&feature=youtu.be)


--------

## Video Import Script

```sh
usage: importer.py [-h] [-v] [-r REGEX] [-c] [-s STORAGE] [-f FOLDER]
                   [-i HOST] [-p PORT] [-m HOOK_MODULE]

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         log more info
  -r REGEX, --regex REGEX
                        regex to find camera name
  -c, --csv             dump csv log file
  -s STORAGE, --storage STORAGE
                        location of the local storage db
  -f FOLDER, --folder FOLDER
                        folder to process
  -i HOST, --host HOST  the segmenter ip
  -p PORT, --port PORT  the segmenter port number
  -m HOOK_MODULE, --hook_module HOOK_MODULE
                        hook module for custom functions

```

The video-importer will traverse a trajectory, parse the located video-files for camera-name and video-timestamp data,
register the cameras and finally send the videos to a segmentation service. 

### Metadata Extraction with `--regex`

Services often need to know metadata about a given video, examples are the timestamp of the video or the camera that the 
video originated from. This data is extracted from the video file names according to a regex that is passed in by the user.
The data extracted from the regex consists of: 

1. The camera name that the video came from
2. The timestamp of the video file (the actual timestamp from when the video was recorded)

The importer script will go over the directory of video files and parse out the attributes given above. For each new camera it finds (based on the camera name) 
it will call the camera-registration function discussed below, and the timestamp will be passed to the video-content-post function
also discussed in the next section.

*Example*

Let's say you had videos in a directory of the format

`CAMERA_FRONT-rand-1475973147.mp4`
`CAMERA_FRONT-rand-1475973267.mp4`
`CAMERA_FRONT-rand-1475973350.mp4`

Then you would supply something like the following regex to the importer script:

`.*/(?P<camera>\w+?)\-.*\-(?P<epoch>\d+)\.mp4`

This regex would put `CAMERA_FRONT` into the `camera` variable (which the importer uses internally to hold the camera name) and would put the `14759753350` value into the
`epoch` variable, which represents the Unix timestamp for the video. 


### Hook Module

This video-importer is designed to work with any service that can ingest video for segmentation and processing. How the
importer interacts with that service is determined by the functions defined in the hooks-module that is passed in. The hooks
module is a python script that defines the following functions


#### Camera Registration Function

Some services need to have cameras registered with them before videos from those cameras can be processed by the service.
To deal with this, the video-importer will call the `register_camera` function defined in the hooks-module you pass in. If
no registration is needed one only has to return a unique ID for the camera, which can itself be the camera name. The importer
uses this ID to keep track of what files have been uploaded for which cameras.

An example of this function interacting with a service can be found in the [camio_hooks.py module](https://github.com/CamioCam/examples/blob/john/batch_import/camio_hooks.py).

```python
def register_camera(camera_name, host=None, port=None):
    """
    arguments:
        camera_name   - the name of the camera (as parsed from the filename) 
        host          - the URI/IP address of the segmenter being used
        port          - the port to access the webserver of the segmenter
    returns: this function returns the Camio-specific camera ID.
                 
    description: this function is called when a new camera is found by the import script, 
                 if a camera needs to be registered with a service before content from that
                 camera can be segmented then the logic for registering the camera should 
                 exist in this function.
    """
    pass
```

#### POST Video Content Function

After cameras have been registered, the importer program will loop over the files in the directory and send
them to the importer web-service. It will pass in the host and port information of the web-server, the camera-ID as returned
by the camera-registration function call discussed in the previous section, the path to the video file, and the timestamp
parsed from the video file in the `YYYY-mm-ddTHH:MM:SS.fff` format (ISO8601 UTC). This function should load the video file,
assemble the meta-data in whichever way is required by the segmentation service, and pass the video along.


```python
def post_video_content(host, port, camera_name, camera_id, filepath, timestamp, latlng=None):
    """
    arguments:
        host        - the url of the segmenter
        port        - the port to access the webserver on the segmenter
        camera_name - the parsed name of the camera
        camera_id   - the ID of the camera as returned from the service
        filepath    - full path to the video file that needs segmentation
        timestamp   - the starting timestamp of the video file
        latlng (opt) - the lat/long of the camera (as parsed from the filename)
    returns: true/false based on success
    
    description: this function is called when we find a video for a specific camera, we call
                 this function where the logic should exist to post the file content to a video
                 segmenter.
    """
    pass
```
