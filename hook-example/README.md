# Camio Hooks

## Introduction

Camio provides an image processing pipeline. Videos are uploaded to the Camio cloud from
a phone or an RTSP camera or a Camio Box. The Camio image pipeline provides a labeling 
service but also allows you to register your own labeling hooks. A hook is defined as a custom web service that can compute labels from images.

As videos are uploaded to Camio, they are broken into events,
which are classified as boring, motion, and interesting. Interesting events are pre-classified by the Camio service, labeled, and a significative images are extracted from the videos in the event. If you have registsred a hook, and the event labels match your hook filter, the images beloging to the event are POSTed to your hook URL in the form of a JSON payload. Your hook URL should record the JSON payload, decoded it, extract the images, label them, and then POST the labels back to Camio at the callback_url provided by the initial hook call. The new labels are added to the event.

Remember your hook labels events, not images, or videos. One event may contain mutiple images and multiple videos. The same video can span multiple consecutive events. At this time we only send to your hook preprocessed images. Also, you only label events that Camio has alreday pre-filtered for you as interesting.

## Installing the example hook code

The attached code include an installation script for Debian/Ubuntu 

   hook-install.sh

and an example of a hook:

   hook-example.py

You can run the install with 

   ./hook-install.sh

and it will install the required dependencies and start two processes:

- a web server that received the hook calls and enqueues requests
- a background process that handles the requests and posts back labels to Camio

The queue is implemented as a mongodb database collection.

## The example hook

Our hook-example.py depends on bottle (0.13), gunicorn, requests, PIL, and pymongo.

The hook-example.py code is build on bottle.py 0.13 and intended to work any WSGI web 
server. We recommend gunicorn (a prefork WSGI server) and our install script assumes it.
Once you have all the dependencies installed you can start the web server with:

    nohup gunicorn -w 2 app:hook-example -b 0.0.0.0:8000 > /tmp/gunicorn.log &

Here 8000 is the post to be used and 0.0.0.0 refers to (any IP address). 
-w 2 requests two web server workers and /tmp/gunicorn.log is the location of the logfile.

The server will expose three endpoints:

- http://{your domain}:8000/tasks/ (GET) which you can call to check the service is running
- http://{your domain}:8000/tasks/{api_key} (POST) which will you have to register with Camio and be called by Camio to post event images
- http://{your domain}:8000/tasks/{api_key} (GET) which you can call to obtain a list of pending tasks

The {api_key} is your own API key and you can make it up to be whatever you want. It has to match the API_KEY global variable in the example code. The purpose of the API_KEY is to allow Camio to gain access to your hook and prevent un-authroized access.

Long with the web server you must start the background process:

    nohup python hook-example.py > /tmp/taskqueue.log &

The background process retrieves pending tasks collected by the hook and posts computed labels back to Camio. They will be added to the originating event.

The hook-example.py depends on the following function:

    def compute_labels(images):
        labels = []
        for image in images:
            ...
        labels = ['cat','dog','mouse']
        return labels

This does nothing more than returning the same three labels (cat, dog, mouse) for each 
event but you can edit it to user your favorite ML or NN tool such as OpenCV or Tensorflow,
to perform Object Detection and compute labels from the images.

## registering the hook

Once a hook is created you must tell Camio about it. You must all tell Camio which events
you want to be sent to your hook. This is done by registering an event.

This is a two step process:

- Login into Camio.com and goto: https://camio.com/settings/integrations
  There click on "Generate Token" to obtain a "Developer OAuth Token".
  
- Using curl or other tool register the hook:

    curl \
    -H "Content-Type: application/json" \
    -H "Authorization: token {your develper oauth token}" \
    -d '{"callback_url": "http://{your domain}:8000/tasks/{api_key}", "type": "label_hit", "parsedQuery": "camera == 'mycamera'"}
    -X POST https://www.camio.com/api/users/me/hooks

Here "http://{your domain}:8000/tasks/{api_key}" is the location of your hook including the api_key you have selected (not the same as your develper oauth token). parsedQuery is a string that will be used to filter which events to send to the hook. In the case of the example all those from the camera called 'mycamera'. The parsedQuery allows a subset of the Python syntax. Namely and, or, not, in, <, <=, >, >=, ==, != operators and the following variables:

- camera: the name of the camera uploading the event
- labels: a list of labels alreday associated to the event
- date: the event start date as a python datetime object (date.year, date.day, etc are allowed).

