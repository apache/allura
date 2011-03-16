# Sandbox Creation

We'll use [VirtualBox](http://www.virtualbox.org) and [Ubuntu 10.10](http://ubuntu.com) to create a disposable sandbox for Forge development/testing.

* Download and install [VirtualBox](http://www.virtualbox.org/wiki/Downloads) for your platform.

* Download a minimal [Ubuntu 10.10](https://help.ubuntu.com/community/Installation/MinimalCD) ISO (~15MB).

* Create a new virtual machine in Virtual Box, selecting Ubuntu (64 bit) as the OS type.  The rest of the wizards' defaults are fine.

* When you launch the virtual machine for the first time, you will be prompted to attach your installation media.  Browse to the `mini.iso` that you downloaded earlier.

* Consult [available documentation](https://help.ubuntu.com/) for help installing Ubuntu.


# Forge Installation

Before we begin, you'll need the following additional packages in order to work with the Forge source code.

    ~$ sudo apt-get install git-core gitweb subversion python-svn libtidy-0.99-0

You'll also need additional development packages in order to compile some of the modules.

    ~$ sudo apt-get install default-jdk python-dev libssl-dev libldap2-dev libsasl2-dev

And finally our document-oriented database, MongoDB, and our messaging server, RabbitMQ.

    ~$ sudo apt-get install mongodb rabbitmq-server

## Setting up a virtual python environment

The first step to installing the Forge platform is installing a virtual environment via `virtualenv`.  This helps keep our distribution python installation clean.

    ~$ sudo apt-get install python-setuptools
    ~$ sudo easy_install-2.6 -U virtualenv

Once you have virtualenv installed, you need to create a virtual environment.  We'll call our Forge environment 'anvil'.

    ~$ virtualenv anvil

This gives us a nice, clean environment into which we can install all the forge dependencies.  In order to use the virtual environment, you'll need to activate it.  You'll need to do this whenever you're working on the Forge codebase so you may want to consider adding it to your `~/.bashrc` file.

    ~$ . anvil/bin/activate

Now that that's out of the way, we'll go ahead and install TurboGears.

    (anvil)~$ easy_install pylons==0.9.7
    (anvil)~$ easy_install -i http://www.turbogears.org/2.1/downloads/2.1b2/index/ tg.devtools==2.1b2 TurboGears2==2.1b2
    (anvil)~$ easy_install http://httplib2.googlecode.com/files/httplib2-0.6.0.tar.gz


## Installing the Forge code and dependencies

Now we can get down to actually getting the Forge code and dependencies downloaded and ready to go.

    (anvil)~$ mkdir src
    (anvil)~$ cd src
    (anvil)~/src$ git clone git://git.code.sf.net/p/allura/git.git forge

Although the application setup.py files define a number of dependencies, the `requirements.txt` files are currently the authoritative source, so we'll use those with `pip` to make sure the correct versions are installed.

    (anvil)~/src$ cd forge
    (anvil)~/src/forge$ easy_install pip
    (anvil)~/src/forge$ pip install -r requirements-dev.txt

And now to setup each of the Forge applications for development.  Because there are quite a few (at last count 15), we'll use a simple shell loop to set them up.

    for APP in Allura* Forge* NoWarnings pyforge
    do
        pushd $APP
        python setup.py develop
        popd
    done

Hopefully everything completed without errors.  We'll also need to create a place for Forge to store any SCM repositories that a project might create.

    for SCM in git svn hg
    do
        mkdir -p ~/var/scm/$SCM
        chmod 777 ~/var/scm/$SCM
        sudo ln -s ~/var/scm/$SCM /
    done


## Initializing the environment

The forge consists of several components, all of which need to be running to have full functionality.


### MongoDB database server

Generally set up with its own directory, we'll use ~/var/mongodata to keep our installation localized.  We also need to disable the default distribution server.

    (anvil)~$ sudo service mongodb stop
    (anvil)~$ sudo update-rc.d mongodb remove

    (anvil)~$ mkdir -p ~/var/mongodata ~/logs
    (anvil)~$ nohup mongod --dbpath ~/var/mongodata > ~/logs/mongodb.log &


### SOLR search and indexing server

We have a custom config ready for use.

    (anvil)~$ cd ~/src
    (anvil)~/src$ wget http://apache.mirrors.tds.net/lucene/solr/1.4.0/apache-solr-1.4.0.tgz
    (anvil)~/src$ tar xf apache-solr-1.4.0.tgz
    (anvil)~/src$ cd apache-solr-1.4.0/example/
    (anvil)~/src/apache-solr-1.4.0/example/$ mkdir -p ~/src/forge/solr_config/conf
    (anvil)~/src/apache-solr-1.4.0/example/$ cp solr/conf/solrconfig.xml ~/src/forge/solr_config/conf/
    (anvil)~/src/apache-solr-1.4.0/example/$ nohup java -Dsolr.solr.home=$(cd;pwd)/src/forge/solr_config -jar start.jar > ~/logs/solr.log &


### RabbitMQ message queue

We'll need to setup some development users and privileges.

    (anvil)~$ sudo rabbitmqctl add_user testuser testpw
    (anvil)~$ sudo rabbitmqctl add_vhost testvhost
    (anvil)~$ sudo rabbitmqctl set_permissions -p testvhost testuser ""  ".*" ".*"


### Forge "reactor" processing

Responds to RabbitMQ messages.  We'll need to perform some setup operations before we can start it.

    (anvil)~$ cd ~/src/forge/Allura
    (anvil)~/src/forge/Allura$ paster reactor_setup development.ini
    (anvil)~/src/forge/Allura$ nohup paster reactor development.ini > ~/logs/reactor.log &


### Forge SMTP for inbound mail

Routes messages from email addresses to tools in the forge.

    (anvil)~/src/forge/Allura$ nohup paster smtp_server development.ini > ~/logs/smtp.log &


### TurboGears application server

In order to initialize the Forge database, you'll need to run the following:

    (anvil)~/src/forge/Allura$ paster setup-app development.ini

This shouldn't take too long, but it will start the reactor server doing tons of stuff in the background.  It should complete in 5-6 minutes.  Once this is done, you can start the application server.

    (anvil)~/src/forge/Allura$ nohup paster serve --reload development.ini > ~/logs/tg.log &

And now you should be able to visit the server running on your [local machine](http://localhost:8080/).
You can log in with username test-admin, test-user or root.  They all have password "foo".


## Next Steps


### Generate the documentation

Forge documentation currently lives in the `Allura/docs` directory and can be converted to HTML using `Sphinx`:

    (anvil)~$ cd ~/src/forge/Allura/docs
    (anvil)~/src/forge/Allura/docs$ easy_install sphinx
    (anvil)~/src/forge/Allura/docs$ make html

You will also want to give the test suite a run, to verify there were no problems with the installation.

    (anvil)~$ cd ~/src/forge
    (anvil)~/src/forge$ export ALLURA_VALIDATION=none
    (anvil)~/src/forge$ ./run_tests

Happy hacking!
