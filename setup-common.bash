#!/bin/bash

#
# Install everything (python) into a virtual environment.
# Maybe not important for sandboxes, but important locally.
#

echo '# installing base tools'
sudo easy_install -U setuptools

echo
echo '# setting up a virtual environment'
sudo easy_install -U virtualenv
virtualenv --no-site-packages sandbox-env
. sandbox-env/bin/activate

echo
echo '# installing turbogears'
easy_install ipython
easy_install -i http://www.turbogears.org/2.1/downloads/current/index tg.devtools
easy_install beautifulsoup

#
# Install _our_ code.
#
echo
echo '# cloning forge repo'
git clone ssh://engr.geek.net/forge


#
# Install all our (formal) dependencies.
#
cd forge

echo
echo '# installing pyforge dependencies'
python pyforge/setup.py develop

echo
echo '# installing Ming dependencies'
python Ming/setup.py develop

echo
echo '# installing HelloForge dependencies'
python HelloForge/setup.py develop


# Start up the server?
