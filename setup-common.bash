#!/bin/bash

#
# Install everything (python) into a virtual environment.
# Important in sandboxes to force Python 2.6.  Important
# locally to keep base installs clean.
#

echo '# installing base tools'
sudo easy_install-2.6 -U setuptools

echo
echo '# setting up a virtual environment'
sudo easy_install-2.6 -U virtualenv
virtualenv --no-site-packages sandbox-env
. sandbox-env/bin/activate

# from here on, everything is using Python2.6 from sandbox-env

echo
echo '# installing turbogears'
easy_install ipython
easy_install -UZ -i http://www.turbogears.org/2.1/downloads/current/index turbogears2==2.1a3
easy_install -UZ -i http://www.turbogears.org/2.1/downloads/current/index tg.devtools==2.1a3
easy_install beautifulsoup

#
# Install _our_ code.
#
# echo
# echo '# cloning forge repo'
# git clone ssh://gitosis@engr.geek.net/forge
# cd forge
#
# This already happened just to get this file to run;
# now assume we run it in-place.


#
# Install all our (formal) dependencies.
#

echo
echo '# installing pyforge dependencies'
cd pyforge
python setup.py develop
cd ..

echo
echo '# installing Ming dependencies'
cd Ming
python setup.py develop
cd ..

echo
echo '# installing HelloForge dependencies'
cd HelloForge
python setup.py develop
cd ..

echo
echo '# creating data directory for mongo'
mkdir -p /data/db

echo
echo '# downloading and untarring solr'
mkdir download install
cd download
wget http://apache.mirrors.tds.net/lucene/solr/1.4.0/apache-solr-1.4.0.tgz
cd ../install
tar xzf ../download/apache-solr-1.4.0.tgz

# Start up the server?
