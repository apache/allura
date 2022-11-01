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

To install without Docker requires installing and configuring many services.  See :ref:`step-by-step-install`.

.. _docker-install:

Using Docker
------------

First run
^^^^^^^^^

`Download the latest release <http://www.apache.org/dyn/closer.cgi/allura/>`_ of Allura, or `clone from git <https://forge-allura.apache.org/p/allura/git/ci/master/tree/>`_ for the bleeding edge.

Install `Docker <http://docs.docker.com/installation/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_.
On Linux, you may need to `create a docker group <https://docs.docker.com/engine/install/linux-postinstall/>`_.

.. note::

   For a production-ready Allura, follow the instructions in :file:`Allura/production-docker-example.ini`.
   Then run :code:`export COMPOSE_FILE=docker-compose-prod.yml` and continue running the following commands.
   This will give you HTTPS, settings for better performance and no debugging, and only expose necessary ports.

.. note::

   If you are running Docker inside a VM (or access it by a different hostname for any reason), edit
   :file:`Allura/docker-dev.ini` and add these lines after :code:`[app:main]`

   .. code-block:: ini

      domain = hostname-or-ip
      base_url = http://hostname-or-ip:8080

   Replace :kbd:`hostname-or-ip` with the actual hostname or external IP address.  If you change this setting later,
   just run :kbd:`docker-compose restart web`


Run the following commands in your allura directory:

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

You're up and running!  Visit localhost:8080 (or whatever IP address you're running Docker on).  Then
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

- :file:`./allura-data/virtualenv/bin/python`

Services data:

- :file:`./allura-data/mongo` - mongo data
- :file:`./allura-data/solr` - SOLR index
- :code:`./allura-data/scm/{git,hg,svn}` - code repositories
- :file:`./allura-data/scm/snapshots` - generated code snapshots


.. note::
    
    The :code:`./allura-data/` path can be overriden by setting the LOCAL_SHARED_DATA_ROOT environment variable

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

    docker-compose logs -f

You can specify one or more services to view logs only from them, e.g. to see
outgoing mail:

.. code-block:: bash

    docker-compose logs -f outmail

Update requirements and reinstall apps:

.. code-block:: bash

    docker-compose run web pip install -r requirements.txt
    docker-compose run web ./rebuild-all.bash

You may want to restart at least "taskd" container after that in order for it to
pick up changes.  Run :code:`docker-compose restart taskd`

Run all tests:

.. code-block:: bash

    docker-compose run web ./run_tests

Running subset of tests:

.. code-block:: bash

    docker-compose run web bash -c 'cd ForgeGit && pytest forgegit/tests/functional/test_controllers.py::TestFork'

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
carefully and make changes for production use.  See also :file:`production-docker-example.ini` which sets a variety
of settings better for production (you will always need to customize some values like keys and domains).

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

    ~$ python -c 'import secrets; print(secrets.token_hex(20));'

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
    ~$ mod_wsgi-express start-server development.ini --application-type paste --user allura --group allura --port 8080  --python-path /PATH/TO/VIRTUALENV/lib/python3.7/site-packages/

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
emails sent to that address will be added as comments on the ticket.  With Docker, this is already running on port 8825.
If you are not running docker, run:

.. code-block:: bash

    nohup paster smtp_server development.ini > /var/log/allura/smtp.log &

By default this uses port 8825.  Depending on your mail routing, you may need to change that port number.
And if the port is in use, this command will fail.  You can check the log file for any errors.
To change the port number, edit :file:`development.ini` and change :samp:`forgemail.port` to the appropriate port number for your environment.

You will need to customize your mail server to route mail for Allura to this service.  For example with postfix you can
use :samp:`transport_maps` with::

    mydomain.com smtp:127.0.0.1:8825
    .mydomain.com smtp:127.0.0.1:8825
    *.mydomain.com smtp:127.0.0.1:8825

Various other settings may be necessary depending on your environment.

SMTP in development
^^^^^^^^^^^^^^^^^^^

The following command can be used for quick and easy monitoring of outgoing email during development.

.. code-block:: bash

    docker-compose logs -f outmail

If you are running locally without docker, run this command.  Be sure the port matches the :samp:`smtp_port` from
your :file:`development.ini` (8826 by default).

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
