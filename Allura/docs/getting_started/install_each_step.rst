..     Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.

.. _step-by-step-install:

*************************
Step-by-Step Installation
*************************

.. contents::
   :local:

For a simpler setup using Docker images, see :ref:`docker-install` instead.

In these instructions, we'll use `VirtualBox <http://www.virtualbox.org>`__ and `Ubuntu 18.04 <http://ubuntu.com>`_  to create a disposable sandbox for Allura development/testing.  Allura should work on other Linux systems (including OSX), but setting up all the dependencies will be different.

* Download and install `VirtualBox <http://www.virtualbox.org/wiki/Downloads>`__ for your platform.

* Download a minimal `Ubuntu 18.04 64-bit ISO <https://help.ubuntu.com/community/Installation/MinimalCD>`_.

* Create a new virtual machine in Virtual Box, selecting Ubuntu (64 bit) as the OS type.  The rest of the wizards' defaults are fine.

* When you launch the virtual machine for the first time, you will be prompted to attach your installation media.  Browse to the :file:`mini.iso` that you downloaded earlier.

* After a text-only installation, you may end up with a blank screen and blinking cursor.  Press :code:`Alt-F1` to switch to the first console.

* Consult `available documentation <https://help.ubuntu.com/>`_ for help installing Ubuntu.


System Packages
^^^^^^^^^^^^^^^

Before we begin, you'll need to install some system packages.  Allura currently supports Python 3.7.

.. code-block:: bash

    ~$ sudo apt-get update
    ~$ sudo apt-get install software-properties-common
    ~$ sudo add-apt-repository ppa:deadsnakes/ppa
    ~$ sudo apt-get update
    ~$ sudo apt-get install git-core python3.7 python3.7-dev gcc libmagic1 libssl-dev libldap2-dev libsasl2-dev libjpeg8-dev zlib1g-dev libffi-dev

To install MongoDB, follow the instructions `here <https://docs.mongodb.org/manual/tutorial/install-mongodb-on-ubuntu/>`_.

Optional, for SVN support:

.. code-block:: bash

    ~$ sudo apt-get install subversion libsvn-dev make g++ python3-svn

Setting up a python virtual environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The first step to installing the Allura platform is installing a virtual environment via :code:`venv`.  This helps keep our distribution python installation clean.

.. code-block:: bash

    ~$ sudo apt-get install python3.7-venv

Then create a virtual environment.  We'll call our Allura environment 'env-allura'.

.. code-block:: bash

    ~$ python3.7 -m venv env-allura

This gives us a nice, clean environment into which we can install all the allura dependencies.
In order to use the virtual environment, you'll need to activate it:

.. code-block:: bash

    ~$ source env-allura/bin/activate

You'll need to do this whenever you're working on the Allura codebase so you may want to consider adding it to your :file:`~/.bashrc` file.

Creating the log directory
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    (env-allura)~$ sudo mkdir -p /var/log/allura
    (env-allura)~$ sudo chown $(whoami) /var/log/allura

Installing the Allura code and dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Now we can get down to actually getting the Allura code and dependencies downloaded and ready to go.  If you don't have the source code yet, run:

.. code-block:: bash

    (env-allura)~$ mkdir src
    (env-allura)~$ cd src
    (env-allura)~/src$ git clone https://gitbox.apache.org/repos/asf/allura.git/

If you already reading this file from an Allura release or checkout, you're ready to continue.

We'll upgrade `pip <https://pip.pypa.io/en/stable/>`_ to make sure its a current version, and then install all Allura python dependencies with it.

.. code-block:: bash

    (env-allura)~/src$ cd allura
    (env-allura)~/src/allura$ pip install -U pip
    (env-allura)~/src/allura$ pip install -r requirements.txt

This may take a little while.

Optional, for SVN support: install the wheel package then use the pysvn-installer script to build a pysvn wheel.

.. code-block:: bash

    (env-allura)~/src/allura$ pip install wheel
    (env-allura)~/src/allura$ curl https://raw.githubusercontent.com/reviewboard/pysvn-installer/master/install.py | python

Next, run this to set up all the Allura tools:

.. code-block:: bash

    (env-allura)~/src/allura$ ./rebuild-all.bash

.. note::

    If you only want to use a few tools, run this instead:

    .. code-block:: bash

        (env-allura)~/src/allura$ cd Allura
        (env-allura)~/src/allura/Allura$ python setup.py develop
        (env-allura)~/src/allura/Allura$ cd ../ForgeWiki   # required tool
        (env-allura)~/src/allura/ForgeWiki$ python setup.py develop
        # repeat for any other tools you want to use

Initializing the environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Allura forge consists of several components, all of which need to be running to have full functionality.

SOLR search and indexing server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We have a custom config ready for use.

.. code-block:: bash

    (env-allura)~$ cd /tmp
    (env-allura)/tmp$ sudo apt-get install openjdk-8-jre-headless unzip
    (env-allura)/tmp$ wget -nv https://archive.apache.org/dist/lucene/solr/5.3.1/solr-5.3.1.tgz
    (env-allura)/tmp$ tar xvf solr-5.3.1.tgz solr-5.3.1/bin/install_solr_service.sh --strip-components=2
    (env-allura)/tmp$ sudo ./install_solr_service.sh solr-5.3.1.tgz

    (env-allura)/tmp$ cd ~/src/allura
    (env-allura)~/src/allura$ sudo -H -u solr bash -c 'cp -R solr_config/allura/ /var/solr/data/'
    (env-allura)~/src/allura$ sudo service solr start


Create code repo directories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The default configuration stores repos in :file:`/srv`, so we need to create those directories:

.. code-block:: bash

    ~$ sudo mkdir /srv/{git,svn,hg}
    ~$ sudo chown $USER /srv/{git,svn,hg}
    ~$ sudo chmod 775 /srv/{git,svn,hg}

If you don't have :code:`sudo` permission or just want to store them somewhere else, change the :file:`/srv` paths in :file:`development.ini`

If you want to set up remote access to the repositories, see :ref:`scm_hosting`

Allura task processing
~~~~~~~~~~~~~~~~~~~~~~

Allura uses a background task service called "taskd" to do async tasks like sending emails, and indexing data into solr, etc.  Let's get it running

.. code-block:: bash

    (env-allura)~$ cd ~/src/allura/Allura
    (env-allura)~/src/allura/Allura$ nohup paster taskd development.ini > /var/log/allura/taskd.log 2>&1 &


A few more steps, if using git
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're using a released version of Allura, these are already done for you.  These commands will prepare final JS & CSS files.
For non-Ubuntu installations see https://nodejs.org/en/download/package-manager/ for other options to replace the first line here:

.. code-block:: bash

    (env-allura)~$ curl --silent --location https://deb.nodesource.com/setup_10.x | sudo bash -
    (env-allura)~$ sudo apt-get install nodejs
    (env-allura)~$ cd ~/src/allura
    (env-allura)~$ npm ci
    (env-allura)~$ npm run build


The application server
~~~~~~~~~~~~~~~~~~~~~~

In order to initialize the Allura database, you'll need to run the following:

For development setup:

.. code-block:: bash

    (env-allura)~/src/allura/Allura$ paster setup-app development.ini

For production setup:

.. code-block:: bash

    (env-allura)~/src/allura/Allura$ ALLURA_TEST_DATA=False paster setup-app development.ini

This shouldn't take too long, but it will start the taskd server doing tons of stuff in the background.  Once this is done, you can start the application server:

.. code-block:: bash

    (env-allura)~/src/allura/Allura$ gunicorn --reload --paste development.ini -b :8080  # add --daemon to run in the background

Next Steps
^^^^^^^^^^

Go to the Allura webapp running on your `local machine <http://localhost:8080/>`_ port 8080.

* Read :ref:`post-setup-instructions`
* Ask questions and discuss Allura on the `allura-dev mailing list <http://mail-archives.apache.org/mod_mbox/allura-dev/>`_
* Run the test suite (slow): :code:`$ ALLURA_VALIDATION=none ./run_tests`
* File bug reports at https://forge-allura.apache.org/p/allura/tickets/new/ (login required)
* Contribute code according to :ref:`this guide <contributing>`
