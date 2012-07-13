#!/bin/bash

if [ -z "$VIRTUAL_ENV" ]; then
	echo "You need to activate your virtualenv first!";
	exit;
fi

echo 'Getting latest code with `git pull` ...'
git pull

echo 'Updating python packages with `pip install -r requirements.txt` ...'
pip install -r requirements.txt
if [ "$?" -gt 0 ]; then
	echo
	echo
	echo 'Command `pip install -r requirements.txt` failed.  Sometimes this is a random download error.  If so, just try again.'
	exit;
fi

./rebuild.bash

echo 'If you have taskd or the web server running, you should restart them now.'