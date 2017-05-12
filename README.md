video-importer
==============

Traverses directories to import video as segmented events with correct timestamps and metadata. 
For background, see the [Product Requirements Document](https://docs.google.com/document/d/1TTkzQqDA9KoKL5RvhYVJqtrcXoDJuwyFnCnorg_VM30/edit?usp=sharing).

## What is it
The importer is an Open Source project to automate the ingestion of video files so that they can be labeled by advanced classifiers
running either locally or in the cloud.

## Who is it for
The Importer is for all Electronic Monitoring (EM) services that record video for fisheries observation to report scientific and
regulatory data quickly.

## Why is it needed
The review and labeling of recorded video is slow. In fact, the elapsed time to review is often longer than the fishing trip's duration.
Until boats at-sea have the compute power and bandwidth sufficient to analyze, extract and upload data in real-time, the video review must
start with the on-shore processing of hard drives filled with recorded video. 

The importer makes it fast and simple to create labeled video bookmarks automatically so that the EM's own review tools and processes can
jump to the relevant video segments rather than wade through hours of video. For example, the reviewer can jump directly to events in
which tuna or marlin was brought on board as in [this demo](https://www.youtube.com/watch?v=0BUWRHd_jss&feature=youtu.be)


--------
--------

## Running the Importer

To get a simple overview of importer and how to use it, try running this from a shell:

```sh
python importer.py --help
```

Which will output:

```man
usage: importer.py [-h] [-r REGEX] [-c] [-s STORAGE] [-f FOLDER] [-i HOST]
                   [-p PORT] [-m HOOK_MODULE] [-d HOOK_DATA_JSON] [-v] [-q]

optional arguments:
  -h, --help            show this help message and exit
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
                        full path to hook module for custom functions (a
                        python file)
  -d HOOK_DATA_JSON, --hook_data_json HOOK_DATA_JSON
                        a json-dictionary containing extra information to be
                        passed to the hook-module
  -v, --verbose         set logging level to debug
  -q, --quiet           set logging level to errors only
```

The video-importer will traverse a directory to extract the camera-name and video-timestamp from the video filenames,
register the cameras with the requested hook services, and submit the video files for event segmentation and labeling.

### Metadata Extraction with `--regex`

Services often need to know metadata about a given video. For example, the timestamp at which the video was recorded and 
the name of the camera that recorded it are required. 
This data is extracted from the video filenames according to a regular expression provided by the `--regex` parameter.
The minimum data extracted by the regex includes the:

1. *camera name* that recorded the video
2. *timestamp* at which the video was recorded

As the importer identifies new camera names in traversing the directories,  it will call the **camera-registration** function using
the camera name discovered and will call the **video-content-post** function using the timestamp and camera name.

*Example*

Let's say video files in a directory filenames that include the camera name and Unix epoch timestamp in the filenames like this:

`CAMERA_FRONT-rand-1475973147.mp4`
`CAMERA_FRONT-rand-1475973267.mp4`
`CAMERA_FRONT-rand-1475973350.mp4`

Then you would supply this `--regex` parameter value for the importer script:

`.*/(?P<camera>\w+?)\-.*\-(?P<epoch>\d+)\.mp4`

The first capture group assigns the value `CAMERA_FRONT` to the `camera` variable, which the importer uses as the camera name, and 
the second capture group assigns the value `14759753350` to the `epoch` variable, which is the Unix timestamp of the first frame of the video.


### Hook Module

The video-importer is designed to work with any service that can ingest video for event segmentation and labeling. 
The hooks-module specifies a python module with these functions used to interact with the desired services:

1. `register_camera` - Informs the service about a new camera that has been found
2. `post_video_content` - Sends the video data to the segmenter via a POST
3. `set_hook_data` - Sets hook-specific data (specific to auth, camera data, etc.)


#### Camera Registration Function

Some services require that cameras be registered with the service before submitting the videos for processing.
So the video-importer calls the `register_camera` function defined in the hooks-module you specify. 
If no camera registration is required, then the `register_camera` function can return a unique ID for the camera, even 
if the ID is simply the camera name. 
The importer uses this camera ID to keep track of which video files have been processed for particular cameras.

An example of this function interacting with a service can be found in the [camio_hooks.py module](https://github.com/CamioCam/examples/blob/master/batch_import/camio_hooks.py).

```python
def register_camera(camera_name, host=None, port=None):
    """
    arguments:
        camera_name   - the name of the camera (as parsed from the filename) 
        host          - the URI/IP address of the segmenter being used #TODO(carter) should be server with path?
        port          - the port to access the webserver of the segmenter
    returns: this function returns the Camio-specific camera ID.
                 
    description: this function is called when a new camera is found by the video-importer.
                 If a camera needs to be registered with a service before content from that
                 camera can be segmented/labeled, then put the code for registering the
                 camera inside this function. If not then return your own unique ID (even if just the camera name)
    """
```

#### POST Video Content Function

After cameras have been registered, the video-importer loops over the video files in the directory and sends
them to the segmenter with all the information collected from the files and from the camera registration.
The importer supplies the timestamp in ISO8601 format UTC like `YYYY-mm-ddTHH:MM:SS.fff`. 
The `post_video_content` function should load the video file, assemble the meta-data in whichever way is required by 
the chosen segmentation service, and pass the video along.


```python
def post_video_content(host, port, camera_name, camera_id, filepath, timestamp, latlng=None):
    """
    arguments:
        host        - the url of the segmenter # TODO(carter) call this url or server since host is confusing.
        port        - the port to access the webserver on the segmenter
        camera_name - the parsed name of the camera
        camera_id   - the ID of the camera as returned from the register_camera function
        filepath    - full path to the video file that needs segmentation
        timestamp   - the earliest timestamp contained in the video file
        location (opt) - a string describing the location of the camera. 
                         example: {"location": {"lat": 7.367598, "lng":134.706975}, "accuracy":5.0}
    returns: true/false based on success
    
    description: this function is called each time the importer finds a video for a specific camera. 
                 Put the code for posting the video and meatadata to the segmenter inside this function.
    """
    pass
```

#### Set Hook Data Function

Sometimes there is extra data that the hook-module needs from the user but is not explicitely defined in the importer arguments,
you can pass this data in using the `--hook_data_json` argument. Simple give something like 

```
python importer "... some arguments here..." --hook_data_json '{"camera_plan": "pro", "user_id": "AABBCCDD"}'
```

And the json-dictionary that you define will be de-serialized into a python dictionary and passed to the `set_hook_data` function defined
in the hook-module you submit (should that function exist). This function looks like this:

```python
def set_hook_data(data_dict):
    """
    arguments:
        data_dict    - a python dictionary full of values passed in by the user in the `--hook_data_json` argument. Includes a reference
                       to the logging object that is being used by the importer so that the hooks-module can log in a similar fashion
    returns: nothing
    """
    pass
```


