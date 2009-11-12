#!/bin/bash

#
# Install everything (python) into a virtual environment.
# Maybe not important for sandboxes, but important locally.
#

sudo easy_install -U setuptools
sudo easy_install -U virtualenv
virtualenv --no-site-packages sandbox-env
. sandbox-env/bin/activate

easy_install ipython
easy_install -i http://www.turbogears.org/2.1/downloads/current/index tg.devtools

#
# Install _our_ code.
#
git clone ssh://engr.geek.net/forge


#
# Install all our (formal) dependencies.
#
cd forge/pyforge
python setup.py develop


# Start up the server?
