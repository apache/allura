Getting Started Guide
=====================

Quickstart Script
----------------------

If you have or can acquire a copy of the quickstart script setup-local.bash,
that's probably the way to go.  For those who are gluttons for punishment, here
are the manual directions....

Setup your python development stack on a Mac
--------------------------------------------
If you use a mac, you'll want to follow the `Mac OS install`_ instructions now.

.. _`Mac OS install`: mac_install.html

Setting up a virtual environment
------------------------------------------

The first step to installing the Forge platform is installing a virtual
environment ("virtualenv").  To do this, you need to first download a copy of
`ez_setup.py <http://peak.telecommunity.com/dist/ez_setup.py>`_.  Once you have
this, you need to install virtualenv.  You can do this by executing::

    $ sudo python ez_setup.py virtualenv

Once you have virtualenv installed, you need to create a virtual environment.
We'll call our environment 'anvil'::

    $ virtualenv anvil --no-site-packages

This gives us a nice, clean environment into which we can install all the forge
dependencies.  In order to use the virtual environment, you'll need to activate
it::

    ~$ . anvil/bin/activate
    (anvil)~$ 

Now that that's out of the way, we'll go ahead and install turbogears::

    (anvil)~$ easy_install -i http://www.turbogears.org/2.1/downloads/current/index tg.devtools TurboGears2

Installing the code
-------------------------

.. sidebar:: System Required Packages

    Before performing the steps below, you'll want to make sure you have the
    following packages installed on your system.  (There may be others, these are
    the ones I know about at the moment.)

    - python-dev
    - libldap2-dev
    - libsasl2-dev
    - rabbitmq-server

OK, now we can get down to actually getting the forge code and dependencies
downloaded and ready to go.  The first thing we'll need to set up is `Ming
<http://merciless.sourceforge.net>`_.  To do this, we'll check out the source
from git::

    (anvil)~$ mkdir src
    (anvil)~$ cd src
    (anvil)~/src$ git clone ssh://merciless.git.sourceforge.net/gitroot/merciless/merciless Ming

Now, we'll need to set up Ming for development work::

    (anvil)~/src$ cd Ming
    (anvil)~/src/Ming$ python setup.py develop

Once this is done, we'll check out & set up out forge codebase::

    (anvil)~/src/Ming$ cd ..
    (anvil)~/src$ git clone ssh://engr.geek.net/forge
    (anvil)~/src$ cd forge/pyforge
    (anvil)~/src/forge/pyforge$ python setup.py develop
    (anvil)~/src/forge/pyforge$ cd ../ForgeForum
    (anvil)~/src/forge/ForgeForum$ python setup.py develop
    (anvil)~/src/forge/ForgeForum$ cd ../ForgeMail
    (anvil)~/src/forge/ForgeMail$ python setup.py develop
    (anvil)~/src/forge/ForgeMail$ cd ../ForgeSCM
    (anvil)~/src/forge/ForgeSCM$ python setup.py develop
    (anvil)~/src/forge/ForgeSCM$ cd ../ForgeTracker
    (anvil)~/src/forge/ForgeTracker$ python setup.py develop
    (anvil)~/src/forge/ForgeTracker$ cd ../ForgeWiki
    (anvil)~/src/forge/ForgeWiki$ python setup.py develop
    (anvil)~/src/forge/ForgeWiki$ cd ../HelloForge
    (anvil)~/src/forge/HelloForge$ python setup.py develop
    (anvil)~/src/forge/HelloForge$ cd ..

Hopefully everything completed without errors.

Initializing the environment
-----------------------------------

The forge consists of several components, all of which need to be running to have
full functionality:

mongod
  MongoDB database server -- generally set up with its own directory (I like
  ~/var/mongodata).  To run, execute the following::

      (anvil)~/src$ mkdir -p ~/var/mongodata 
      (anvil)~/src$ mongod --dbpath ~/var/mongodata 

RabbitMQ
  Message Queue -- to set this up for use, you'll need to run the following commands::

      (anvil)~/src$ sudo rabbitmqctl add_user testuser testpw
      (anvil)~/src$ sudo rabbitmqctl add_vhost testvhost
      (anvil)~/src$ sudo rabbitmqctl set_permissions -p testvhost testuser ""  ".*" ".*"

  If you get errors running these, it's likely because rabbit isn't running. It can be run as a daemon (instructions vary per architecture) or directly from a console window, e.g.::

	    $ cd <rabbitmq_server_directory> # not needed on MACOS
	    $ sudo rabbitmq-server

Forge "reactor" server
  This is the server that will respond to RabbitMQ messages.  To set it up to
  receive messages, you'll need to run the following commands::

      (anvil)~/src$ cd forge/pyforge
      (anvil)~/src/forge/pyforge$ paster reactor_setup development.ini
      (anvil)~/src/forge/pyforge$ paster reactor development.ini

Forge SMTP server
  This server routes messages from email addresses to plugins in the forge::
    
      (anvil)~/src/forge/pyforge$ paster smtp_server development.ini

SOLR server
  This is our search and indexing server.  We have a custom config in
  ~/src/forge/solr_config::

      (anvil)~/<path_to_solr>/example$ java -Dsolr.solr.home=~/src/forge/solr_config -jar start.jar

TurboGears application server
  This is the main application that will respond to web requests.  We'll get into
  details later.

In order to initialize the forge database, you'll need to run the following::

    (anvil)~/src/forge/pyforge$ paster setup-app development.ini

This shouldn't take too long, but it will start the reactor server doing tons of
stuff in the background.  It should complete in 5-6 minutes.  Once this is done,
you can start the application server::

      (anvil)~/src/forge/pyforge$ paster serve --reload development.ini

And now you should be able to visit the server running on your 
`local machine <http://localhost:8080/>`_.

Logging In, Getting Around
----------------------------------------------

Part of the base system includes the test_admin and test_user accounts.  The
password for both accounts is `foo`.  The `test` project has several plugins
already configured; to configure more, you can visit the `Admin` plugin
(accessible in the top navigation bar when inside the `test` project).  

Running the Tests
---------------------------------

The test setup is a little bit different from the dev/production setup so as not
to create conflicts between test data and development data.  This section will
tell you how to set up your test environment.

mongod
  We'll need a test MongoDB server to keep from stomping on our development data::

      (anvil)~/src$ mkdir -p ~/var/mongodata-test
      (anvil)~/src$ mongod --port 27108 --dbpath ~/var/mongodata-test

RabbitMQ
  Here, we'll set up a second virtual host for testing.  We also need to set up
  the RabbitMQ queues using reactor_setup::

      (anvil)~/src$ sudo rabbitmqctl add_vhost vhost_testing
      (anvil)~/src$ sudo rabbitmqctl set_permissions -p vhost_testing testuser ""  ".*" ".*"
      (anvil)~/src$ cd forge/pyforge
      (anvil)~/src/forge/pyforge$ paster reactor_setup test.ini#main_with_amqp

SOLR server
  We are using the multicore version of SOLR already, so all the changes to use
  core1 (the testing core) rather than core0 (the dev core) are encapsulated in
  test.ini.

To actually run the tests, just go to the plugin directory you wish to test (or
to the pyforge directory) and type::

    (anvil)~/src/forge/pyforge$ nosetests

Some options you might find useful for nosetests:

--pdb
  Drops into a PDB prompt on unexpected exceptions ("errors" in unittest
  terminology)

--pdb-fail
  Drops into a PDB prompt on AssertionError exceptions in tests  ("failures" in unittest
  terminology)

-s
  Do *not* capture stdout.  This is essential if you have embedded pdb
  breakpoints in your test code.  (Otherwise, you will not see the prompt; your
  test will just mysteriously hang forever.)

-v
  Print the name of the test as it runs.  This is useful if the test suite takes a while
  to run and you want to let it continue to run while you begin debugging the
  first (few) failures.


Happy hacking!
