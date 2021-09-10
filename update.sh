#!/bin/bash

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

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

./rebuild-all.bash

echo 'If you have taskd or the web server running, you should restart them now.'
