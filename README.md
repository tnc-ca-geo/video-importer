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

## Installing the importer

```
git clone https://github.com/tnc-ca-geo/video-importer.git
cd video-importer
python setup.py install
```


## Running the Importer

To get a simple overview of importer and how to use it, try running this from a shell:

```sh
python import_video.py --help
```

Which will output:

```man
usage: import_video.py [-h] [-v] [-q] [-c] [-p PORT] [-r REGEX] [-s STORAGE]
                       [-d HOOK_DATA_JSON] [-f HOOK_DATA_JSON_FILE]
                       folder hook_module host

positional arguments:
  folder                full path to folder of input videos to process
  hook_module           full path to hook module for custom functions (a
                        python file)
  host                  the IP-address or hostname of the segmenter

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         set logging level to debug
  -q, --quiet           set logging level to errors only
  -c, --csv             dump csv log file
  -p PORT, --port PORT  the segmenter port number (default: 8080)
  -r REGEX, --regex REGEX
                        regex to extract input-file meta-data. The two capture
                        group fields are <camera> and <epoch> which capture
                        the name of the camera that the video originates from
                        and the timestamp of the start of the video
                        respectively. (default:
                        ".*/(?P<camera>\w+?)\-.*\-(?P<epoch>\d+)\.mp4")
  -s STORAGE, --storage STORAGE
                        full path to the local storage db (default:
                        ./.processes.shelve)
  -d HOOK_DATA_JSON, --hook_data_json HOOK_DATA_JSON
                        a json object containing extra information to be
                        passed to the hook-module
  -f HOOK_DATA_JSON_FILE, --hook_data_json_file HOOK_DATA_JSON_FILE
                        full path to a file containing a json object of extra
                        info to be passed to the hook module.note - the values
                        passed in through this trump the same values passed in
                        through the `-d` param
```

The video-importer will traverse a directory to extract the camera-name and video-timestamp from the video filenames,
register the cameras with the requested hook services, and submit the video files for event segmentation and labeling.

### Metadata Extraction with `--regex`

Services often need to know metadata about a given video. For example, the timestamp at which the video was recorded and 
the name of the camera that recorded it are required. 
This data is extracted from the video filenames according to a regular expression provided by the `--regex` parameter.
The minimum data extracted by the regex includes the:

1. *camera name* (capture group name `<camera>`) that recorded the video
2. *timestamp* (capture group name `<epoch>`) at which the video was recorded

As the importer identifies new camera names while traversing the directory of input videos, it will call the `register_camera` function using
the camera name discovered. Once a camera is registered, when the script finds any videos from that camera it will call the `post_video_content` 
function using the timestamp of the start of that video and the camera name, allowing the segmentation service to keep track of which videos came from
which cameras.

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

The `import_video.py` program is designed to work with any service that can ingest video for event segmentation and labeling. 
The `--hooks_module` argument is used to specify a python module with the following functions that allow the importer to work with your desired service.

1. `register_camera` - Informs the service about a new camera that has been found
2. `post_video_content` - Sends the video data to the segmenter via a POST
3. `set_hook_data` - Sets hook-specific data (specific to auth, camera data, etc.)

An example of the structure of these functions can be found in the [`hooks_template.py`](hooks_template.py) file, or below in 
the following 3 subsections.

#### `register_camera` Function

Some services require that cameras be registered with the service before submitting the videos for processing,
so the `import_video.py` program calls the `register_camera` function defined in the hooks-module you specify before
sending any videos from that camera for segmentation.
If no camera registration is required, then the `register_camera` function can return a unique ID for the camera, even 
if the ID is simply the camera name. 
The importer uses this camera ID to keep track of which video files have been processed for particular cameras.

An example of this function interacting with a service can be found in the [camio_hooks.py module](https://github.com/CamioCam/examples/blob/master/batch_import/camio_hooks.py).

```python
def register_camera(camera_name, host=None, port=None):
    """
    arguments:
        camera_name   - the name of the camera (as parsed from the filename)
        host          - the URI/IP address of the segmenter being used
        port          - the port to access the webserver of the segmenter
    returns: this function returns a dictionary describing the new camera
             NOTE: the response from the register_camera function must include a field named camera_id,
             which is the unique ID assigned by the service used to register this camera_name.

    description: this function is called when a new camera is found by the import script.
                 If a camera needs to be registered with a service before content from that
                 camera can be segmented then the logic for registering the camera should
                 exist in this function.
    """
```

#### `post_video_content` Function 

After cameras have been registered, the video-importer loops over the video files in the directory and sends
them to the segmenter with all the information collected from the files and from the camera registration.
The importer supplies the timestamp in ISO8601 format UTC like `YYYY-mm-ddTHH:MM:SS.fff`. 
The `post_video_content` function should load the video file, assemble the meta-data in whichever way is required by 
the chosen segmentation service, and pass the video along.


```python
def post_video_content(host, port, camera_name, camera_id, filepath, timestamp, latlng=None):
    """
    arguments:
        host        - the url of the segmenter
        port        - the port to access the webserver on the segmenter
        camera_name - the parsed name of the camera
        camera_id   - the ID of the camera as returned from the service
        filepath    - full path to the video file that needs to be uploaded for segmentation
        timestamp   - the starting timestamp of the video file
        location(opt) - a json-string describing the location of the camera
                        Example {"location:" {"lat": 7.367598, "lng":134.706975}, "accuracy":5.0}
    returns: true/false based on success

    description: This function is called each time a new video file is found for a specific camera, so 
                 add the logic required to ingest each video for segmentation and labeling here. 
                 For example, when using Camio, the HTTP POST to the segmenter resides here.
    """
```

#### `set_hook_data` Function

Sometimes there is extra data that the hook-module needs from the user but is not explicitly defined in the importer arguments,
you can pass this data in using the `--hook_data_json` argument. Simple give something like 

```
python import_video.py "... some arguments here..." --hook_data_json '{"camera_plan": "pro", "user_id": "AABBCCDD"}'
```

And the json object that you define will be de-serialized into a python dictionary and passed to the `set_hook_data` function defined
in the hook-module you submit (should that function exist). This function looks like this:

```python
def set_hook_data(data_dict):
    """
    arguments:
        data_dict - data for use by the hooks module
    description:
        let the importer pass in any arbitrary data for use by the hooks program
        (e.g. use this to accept plan data or user-account information)
    """
```

