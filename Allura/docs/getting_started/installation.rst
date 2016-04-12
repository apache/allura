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

************
Installation
************

.. contents::
   :local:

.. _step-by-step-install:

Step-by-Step Installation
-------------------------

For a simpler setup using Docker images, see :ref:`docker-install` instead.

In these instructions, we'll use `VirtualBox <http://www.virtualbox.org>`__ and `Ubuntu 14.04 <http://ubuntu.com>`_ (12.04 works too) to create a disposable sandbox for Allura development/testing.  Allura should work on other Linux systems (including OSX), but setting up all the dependencies will be different.

* Download and install `VirtualBox <http://www.virtualbox.org/wiki/Downloads>`__ for your platform.

* Download a minimal `Ubuntu 14.04 64-bit ISO <https://help.ubuntu.com/community/Installation/MinimalCD>`_.

* Create a new virtual machine in Virtual Box, selecting Ubuntu (64 bit) as the OS type.  The rest of the wizards' defaults are fine.

* When you launch the virtual machine for the first time, you will be prompted to attach your installation media.  Browse to the :file:`mini.iso` that you downloaded earlier.

* After a text-only installation, you may end up with a blank screen and blinking cursor.  Press :code:`Alt-F1` to switch to the first console.

* Consult `available documentation <https://help.ubuntu.com/>`_ for help installing Ubuntu.


System Packages
^^^^^^^^^^^^^^^

Before we begin, you'll need to install some system packages.

.. code-block:: bash

    ~$ sudo aptitude install git-core python-dev libssl-dev libldap2-dev libsasl2-dev libjpeg8-dev zlib1g-dev

To install MongoDB, follow the instructions `here <https://docs.mongodb.org/manual/tutorial/install-mongodb-on-ubuntu/>`_.

Optional, for SVN support:

.. code-block:: bash

    ~$ sudo aptitude install subversion python-svn

Setting up a virtual python environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The first step to installing the Allura platform is installing a virtual environment via `virtualenv <https://virtualenv.pypa.io/en/latest/>`_.  This helps keep our distribution python installation clean.

.. code-block:: bash

    ~$ sudo aptitude install python-pip
    ~$ sudo pip install virtualenv

Once you have virtualenv installed, you need to create a virtual environment.  We'll call our Allura environment 'env-allura'.

.. code-block:: bash

    ~$ virtualenv env-allura

This gives us a nice, clean environment into which we can install all the allura dependencies.
In order to use the virtual environment, you'll need to activate it:

.. code-block:: bash

    ~$ . env-allura/bin/activate

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
    (env-allura)~/src$ git clone https://git-wip-us.apache.org/repos/asf/allura.git allura

If you already reading this file from an Allura release or checkout, you're ready to continue.

Although the application :file:`setup.py` files define a number of dependencies, the :file:`requirements.txt` files are currently the authoritative source, so we'll use those with `pip <https://pip.pypa.io/en/stable/>`_ to make sure the correct versions are installed.

.. code-block:: bash

    (env-allura)~/src$ cd allura
    (env-allura)~/src/allura$ pip install -r requirements.txt

This will take a while.  If you get an error from pip, it is typically a temporary download error.  Just run the command again and it will quickly pass through the packages it already downloaded and then continue.

Optional, for SVN support: symlink the system pysvn package into our virtual environment

.. code-block:: bash

    (env-allura)~/src/allura$ ln -s /usr/lib/python2.7/dist-packages/pysvn ~/env-allura/lib/python2.7/site-packages/

Next, run :code:`./rebuild-all.bash` to setup all the Allura applications.  If you only want to use a few tools, run:

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

    (env-allura)~$ cd tmp
    (env-allura)/tmp$ wget -nv http://archive.apache.org/dist/lucene/solr/5.3.1/solr-5.3.1.tgz
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

If you're using a released version of Allura, these are already done for you.  This transpiles JS into a version all browsers support.
For non-Ubuntu installations see https://nodejs.org/en/download/package-manager/ for other options to replace the first line here:

.. code-block:: bash

    (env-allura)~$ curl --silent --location https://deb.nodesource.com/setup_4.x | sudo bash -
    (env-allura)~$ sudo apt-get install nodejs
    (env-allura)~$ cd ~/src/allura
    (env-allura)~$ npm install
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

    (env-allura)~/src/allura/Allura$ gunicorn --reload --paste development.ini  # add --daemon to run in the background

Next Steps
^^^^^^^^^^

Go to the Allura webapp running on your `local machine <http://localhost:8080/>`_ port 8080.
(If you're running this inside a VM, you'll probably have to configure the port forwarding settings)

* Read :ref:`post-setup-instructions`
* Ask questions and discuss Allura on the `allura-dev mailing list <http://mail-archives.apache.org/mod_mbox/allura-dev/>`_
* Run the test suite (slow): :code:`$ ALLURA_VALIDATION=none ./run_tests`
* File bug reports at https://forge-allura.apache.org/p/allura/tickets/new/ (login required)
* Contribute code according to :ref:`this guide <contributing>`

.. _docker-install:

Using Docker
------------

First run
^^^^^^^^^

`Download the latest release <http://www.apache.org/dyn/closer.cgi/allura/>`_ of Allura, or `clone from git <https://forge-allura.apache.org/p/allura/git/ci/master/tree/>`_ for the bleeding edge.

Install `Docker <http://docs.docker.com/installation/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_.
On Linux, you may need to `create a docker group <https://docs.docker.com/engine/installation/linux/ubuntulinux/#create-a-docker-group>`_.  On Mac, make sure
you're in a directory that Virtual Box shares through to the VM (by default, anywhere in your home directory works).

Rename your directory to just "allura" and run the following commands in that directory:

Build/fetch all required images:

.. code-block:: bash

    docker-compose build

Python and JS package setup (and first containers started):

.. code-block:: bash

    docker-compose run web scripts/init-docker-dev.sh

Restart SOLR container, so it will see changes from the command above and create index:

.. code-block:: bash

    docker-compose restart solr

Initialize database with test data:

.. code-block:: bash

    docker-compose run taskd paster setup-app docker-dev.ini

.. note::

   If you want to skip test data creation you can instead run: :code:`docker-compose run -e ALLURA_TEST_DATA=False taskd paster setup-app docker-dev.ini`

Start containers in the background:

.. code-block:: bash

    docker-compose up -d

You're up and running!  Visit localhost:8080, or on a Mac or Windows whatever IP address Docker Toolbox is using.  Then
see our :ref:`post-setup-instructions` and read more below about the Docker environment for Allura.


Containers
^^^^^^^^^^

Allura runs on the following docker containers:

- web
- mongo
- taskd
- solr
- inmail
- outmail

Host-mounted volumes
~~~~~~~~~~~~~~~~~~~~

These are created on first run.

Current directory mounted as :file:`/allura` inside containers.  This means your current source code in your host
environment is shared with the containers.  You can edit Allura code directly, and the containers will reflect your
changes.

Python environment:

- :file:`/allura-data/env-docker/python`
- :file:`/allura-data/env-docker/bin`

Services data:

- :file:`/allura-data/mongo` - mongo data
- :file:`/allura-data/solr` - SOLR index
- :code:`/allura-data/scm/{git,hg,svn}` - code repositories
- :file:`/allura-data/scm/snapshots` - generated code snapshots

Ports, exposed to host system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 8080 - webapp
- 8983 - SOLR admin panel (http://localhost:8983/solr/)
- 8825 - incoming mail listener
- 27017 - mongodb

Useful commands
^^^^^^^^^^^^^^^

Restarting all containers:

.. code-block:: bash

    docker-compose up -d

View logs from all services:

.. code-block:: bash

    docker-compose logs

You can specify one or more services to view logs only from them, e.g. to see
outgoing mail:

.. code-block:: bash

    docker-compose logs outmail

Update requirements and reinstall apps:

.. code-block:: bash

    docker-compose run web pip install -r requirements.txt
    docker-compose run web ./rebuild-all.bash

You may want to restart at least "taskd" container after that in order for it to
pick up changes.  Run :code:`docker-compose restart taskd`

Running all tests:

.. code-block:: bash

    docker-compose run web ./run_tests

Running subset of tests:

.. code-block:: bash

    docker-compose run web bash -c 'cd ForgeGit && nosetests forgegit.tests.functional.test_controllers:TestFork'

Connecting to mongo using a container:

.. code-block:: bash

    docker-compose run mongo mongo --host mongo


.. _post-setup-instructions:

Post-setup instructions
-----------------------

Logging in and sample projects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can log in with username `admin1`, `test-user` or `root`.  They all have password "foo".  (For more details
on the default data, see :file:`bootstrap.py`)

There are a few default projects (like "test") and neighborhoods.  Feel free to experiment with them.  If you want to
register a new project in your own forge, visit `/p/add_project`.

Create project for site-admin
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First of all you need to create a project, which will serve as a container for keeping site administrators (users who will have access to the :ref:`admin interface <site-admin-interface>`).

In order to do that:

- open main page of the site in your browser
- go to "Projects" neighborhood (:ref:`what-are-neighborhoods`)
- click "Register a new project" link

By default all admins of "allura" project in "Projects" neighborhood are treated as site admins. If you want to use different project for that, change `site_admins_project` in :file:`development.ini`.

Change default configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :file:`development.ini` file is geared towards development, so you will want to review
carefully and make changes for production use.

Change `[handler_console]` section, so that logs go to a file and will include background tasks info.

.. code-block:: ini

    class = allura.lib.utils.CustomWatchedFileHandler
    args = ('/path/to/allura.log', 'a')

Add write permissions to the :file:`/path/to/allura.log` for the user you use to run allura proccess.

Change "secrets".

.. code-block:: ini

    beaker.session.secret = <your-secret-key>
    beaker.session.validate_key = <yet-another-secret-key>

The first one is used for simple cookies, the latter is used for encrypted cookies.

You can use the following command to generate a good key:

.. code-block:: bash

    ~$ python -c 'import os; l = 20; print "%.2x" * l % tuple(map(ord, os.urandom(l)))'

Production-quality web server
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you are running on a public facing server, you should check out some of the additional gunicorn configuration options at http://gunicorn.org/.
For example, you'll want multiple worker processes to handle simultaneous requests, proxy behind nginx for added protection, etc.

If you'd like to use another webserver, here are a few options:

`uWSGI <http://uwsgi-docs.readthedocs.org/en/latest/>`_

.. code-block:: bash

    ~$ pip install uwsgi  # or install via system packages
    ~$ uwsgi --ini-paste-logged development.ini --virtualenv /PATH/TO/VIRTUALENV --http 0.0.0.0:8080


`mod_wsgi-express <https://pypi.python.org/pypi/mod_wsgi>`_

.. code-block:: bash

    ~$ pip install mod_wsgi  # requires httpd2 devel libraries installed in the system
    ~$ mod_wsgi-express start-server development.ini --application-type paste --user allura --group allura --port 8080  --python-path /PATH/TO/VIRTUALENV/lib/python2.7/site-packages/

For any other wsgi server (e.g. mod_wsgi with Apache, or waitress) you will need a wsgi callable set up like this:

.. code-block:: python

    from paste.deploy import loadapp
    from paste.script.util.logging_config import fileConfig

    config_file = '/PATH/TO/Allura/development.ini'
    fileConfig(config_file)
    application = loadapp('config:%s' % config_file)



Configuring Optional Features
-----------------------------

The :file:`development.ini` file has many options you can explore and configure.

To run SVN and Git services, see the :doc:`scm_host` page.

Some features may be added as separate `Allura extensions <https://forge-allura.apache.org/p/allura/wiki/Extensions/>`_

Enabling inbound email
^^^^^^^^^^^^^^^^^^^^^^

Allura can listen for email messages and update tools and artifacts.  For example, every ticket has an email address, and
emails sent to that address will be added as comments on the ticket.  To set up the SMTP listener, run:

.. code-block:: bash

    nohup paster smtp_server development.ini > /var/log/allura/smtp.log &

By default this uses port 8825.  Depending on your mail routing, you may need to change that port number.
And if the port is in use, this command will fail.  You can check the log file for any errors.
To change the port number, edit `development.ini` and change `forgemail.port` to the appropriate port number for your environment.

SMTP in development
^^^^^^^^^^^^^^^^^^^

The following command can be used for quick and easy monitoring of smtp during development.
Just be sure the port matches the `smtp_port` from your `development.ini` (8826 by default).

.. code-block:: bash

    python -u -m smtpd -n -c DebuggingServer localhost:8826

This will create a new debugging server that discards messages and prints them to stdout.


Using LDAP
^^^^^^^^^^

Allura has a pluggable authentication system, and can use an existing LDAP system. In your config
file (e.g. :file:`development.ini`), there are several "ldap" settings to set:

* Change auth.method to: :samp:`auth.method = ldap`
* Set all the :samp:`auth.ldap.{*}` settings to match your LDAP server configuration. (:samp:`auth.ldap.schroot_name` won't be
  used, don't worry about it.)
* Keep :samp:`auth.ldap.autoregister = true` This means Allura will use existing users from your LDAP
  server.
* Set :samp:`auth.allow_user_registration = false` since your users already are present in LDAP.
* Change user_prefs_storage.method to :samp:`user_prefs_storage.method = ldap`
* Change :samp:`user_prefs_storage.ldap.fields.display_name` if needed (e.g. if display names are stored
  in a different LDAP attribute).

Restart Allura and you should be all set.  Now users can log in with their LDAP credentials and their
Allura records will be automatically created the first time they log in.

Note: if you want users to register new accounts into your LDAP system via Allura, you should turn
off :samp:`autoregister` and turn on :samp:`allow_user_registration`
