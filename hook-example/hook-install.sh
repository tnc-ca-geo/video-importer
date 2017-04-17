sudo apt-get install mongodb
sudo apt-get install python-dev
pip install bottle gunicorn pymongo requests
nohup gunicorn -w 2 app:hook-example -b 0.0.0.0 > /tmp/gunicorn.log &
nohup python hook-example.py > /tmp/taskqueue.log &
