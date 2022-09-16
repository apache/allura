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


# Various commands needed to set up the Docker environment, but that use shared volumes, so can't be run as part of a Dockerfile image

set -e  # exit if any command fails

echo -e "\nRunning scripts/init-docker-dev.sh\n"

echo -e "Creating SCM directories\n"
mkdir -p /allura-data/scm/{git,hg,svn,snapshots}

echo -e "Creating directory for SOLR data\n"
mkdir -p /allura-data/solr
echo -e "Changing it's permissions to 777 so that container will have access to it\n"
chmod 777 /allura-data/solr

mkdir -p /allura-data/www-misc
echo "# No robots.txt rules here" > /allura-data/www-misc/robots.txt
cp /allura/Allura/allura/public/nf/favicon.ico /allura-data/www-misc/favicon.ico

# share venv to allow update and sharing across containers
rm -rf /allura-data/virtualenv
if [ ! -e /allura-data/virtualenv ]; then
    echo -e "Creating virtualenv\n"
    python3.7 -m venv /allura-data/virtualenv
    /allura-data/virtualenv/bin/pip install -U pip
    /allura-data/virtualenv/bin/pip install -U wheel
    curl https://raw.githubusercontent.com/reviewboard/pysvn-installer/master/install.py | /allura-data/virtualenv/bin/python
    echo # just a new line
fi
source /allura-data/virtualenv/bin/activate

echo -e "Installing python packages\n"
pip install -q -r requirements.txt

/allura/rebuild-all.bash
echo

if [[ ! -e /allura/Allura/allura/public/nf/js/build/transpiled.js ]]; then
            #  || ! -e /allura/Allura/allura/nf/responsive/css/styles.css
  echo -e "Installing npm packages"
  npm ci  # if we want more progress displayed:  --loglevel http

  if [ ! -e /allura/Allura/allura/public/nf/js/build/transpiled.js ]; then
    echo -e "\nCompiling JS"
    npm run build
  fi

#  if [ ! -e /allura/Allura/allura/nf/responsive/css/styles.css ]; then
#    echo -e "\nCompiling CSS"
#    npm run css
#  fi
fi

echo "Done"
