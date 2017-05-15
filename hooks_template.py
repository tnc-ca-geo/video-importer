#!/usr/bin/env python

import sys
import os

"""
This file defines the required template for a given hooks-module to be used with the import_video.py 
script. The `register_camera` and `post_video_content` functions are required, but the `set_hook_data`
is optional and will only be called if it exists
"""

def set_hook_data(data_dict):
    """
    let the importer pass in arbitrary key-value pairs for use by the hooks program
    (we tend to use this to accept plan data or user-account information)
    data_dict: a python list/dictionary of values passed in from the video importer script, passed in by the
                user under the --hook_data_json argument.
    """
    pass


def register_camera(camera_name, host=None, port=None):
    """
    arguments:
        camera_name   - the name of the camera (as parsed from the filename)
        host          - the URI/IP address of the segmenter being used
        port          - the port to access the webserver of the segmenter
    returns: this function returns a dictionary describing the new camera, including the camera ID
             note - it is required that there is at least one property in this dictionary called
             'camera_id', that is the unique ID of the camera as determined by the service this
             function is registering the camera with. This ID will be used by the importer script

    description: this function is called when a new camera is found by the import script,
                 if a camera needs to be registered with a service before content from that
                 camera can be segmented then the logic for registering the camera should
                 exist in this function.
                 For Camio, this function POSTs to /api/cameras/discovered with the new camera
                 entry. It is required that the "acquisition_method": "batch" set in the camera
                 config for it to be known as a batch-import source as opposed to a real-time
                 input source.
    """
    pass


def post_video_content(host, port, camera_name, camera_id, filepath, timestamp, location=None):
    """
    arguments:
        host        - the url of the segmenter
        port        - the port to access the webserver on the segmenter
        camera_name - the parsed name of the camera
        camera_id   - the ID of the camera as returned from the service
        location(opt) - a json-string describing the location of the camera
                        Example {"location:" {"lat": 7.367598, "lng":134.706975}, "accuracy":5.0}
        filepath    - full path to the video file that needs to be uploaded for segmentation
        timestamp   - the starting timestamp of the video file
    returns: true/false based on success

    description: this function is called when we find a video for a specific camera, we call
                 this function where the logic should exist to post the file content to a video
                 segmenter.
    """
    pass
