#!/usr/bin/env python

import sys
import os

"""
This file defines the required template for a given hooks-module to be used with the import_video.py 
script. The `register_camera` and `post_video_content` functions are required, but the `set_hook_data`
is optional and will only be called if it exists.
"""

def set_hook_data(data):
    """
    arguments:
        data_dict - data for use by the hooks module
    description:
        let the importer pass in any arbitrary data for use by the hooks program
        (e.g. use this to accept plan data or user-account information)
    """
    pass


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
    pass


def post_video_content(host, port, camera_name, camera_id, filepath, timestamp, location=None):
    """
    arguments:
        host        - the url of the segmenter
        port        - the port to access the webserver on the segmenter
        camera_name - the parsed name of the camera
        camera_id   - the ID of the camera as returned from the service
        filepath    - full path to the video file that needs to be uploaded for segmentation
        timestamp   - the starting timestamp of the video file
        location(opt) - a string of JSON describing the location of the camera
                        Example {"location": {"lat": 7.367598, "lng":134.706975}, "accuracy":5.0}
    returns: true/false based on success

    description: This function is called each time a new video file is found for a specific camera, so 
                 add the logic required to ingest each video for segmentation and labeling here. 
                 For example, when using Camio, the HTTP POST to the segmenter resides here.
    """
    pass
