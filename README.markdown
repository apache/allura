# Sandbox Creation

We'll use [VirtualBox](http://www.virtualbox.org) and [Ubuntu 11.10](http://ubuntu.com) to create a disposable sandbox for Forge development/testing.

* Download and install [VirtualBox](http://www.virtualbox.org/wiki/Downloads) for your platform.

* Download a minimal [Ubuntu 11.10 64-bit ISO](https://help.ubuntu.com/community/Installation/MinimalCD).

* Create a new virtual machine in Virtual Box, selecting Ubuntu (64 bit) as the OS type.  The rest of the wizards' defaults are fine.

* When you launch the virtual machine for the first time, you will be prompted to attach your installation media.  Browse to the `mini.iso` that you downloaded earlier.

* After a text-only installation, you may end up with a blank screen and blinking cursor.  Press Alt-F1 to switch to the first console.

* Consult [available documentation](https://help.ubuntu.com/) for help installing Ubuntu.


# Forge Installation

Before we begin, you'll need the following additional packages in order to work with the Forge source code.

    ~$ sudo aptitude install git-core subversion python-svn libtidy-0.99-0

You'll also need additional development packages in order to compile some of the modules.  [Use google for additional PIL/jpeg help.](http://www.google.com/search?q=ubuntu+pil+jpeg+virtualenv)

    ~$ sudo aptitude install default-jdk python-dev libssl-dev libldap2-dev libsasl2-dev libjpeg8-dev zlib1g-dev
    ~$ sudo ln -s /usr/lib/x86_64-linux-gnu/libz.so /usr/lib

And finally our document-oriented database, MongoDB

    ~$ sudo aptitude install mongodb-server

If you are using a different base system, make sure you have Mongo 1.8 or better.  If you need to upgrade, you can download the latest from <http://www.mongodb.org/downloads>

## Setting up a virtual python environment

The first step to installing the Forge platform is installing a virtual environment via `virtualenv`.  This helps keep our distribution python installation clean.

    ~$ sudo aptitude install python-pip
    ~$ sudo pip install virtualenv

Once you have virtualenv installed, you need to create a virtual environment.  We'll call our Forge environment 'anvil'.

    ~$ virtualenv --system-site-packages anvil

This gives us a nice, clean environment into which we can install all the forge dependencies.  (The site-packages flag is to include the python-svn package).  In order to use the virtual environment, you'll need to activate it.  You'll need to do this whenever you're working on the Forge codebase so you may want to consider adding it to your `~/.bashrc` file.

    ~$ . anvil/bin/activate

## Installing the Forge code and dependencies

Now we can get down to actually getting the Forge code and dependencies downloaded and ready to go.

    (anvil)~$ mkdir src
    (anvil)~$ cd src
    (anvil)~/src$ git clone git://git.code.sf.net/p/allura/git.git forge

Although the application setup.py files define a number of dependencies, the `requirements.txt` files are currently the authoritative source, so we'll use those with `pip` to make sure the correct versions are installed.

    (anvil)~/src$ cd forge
    (anvil)~/src/forge$ pip install -r requirements-dev.txt

This will take a while.  If you get an error from pip, it is typically a temporary download error.  Just run the command again and it will quickly pass through the packages it already downloaded and then continue.

And now to setup each of the Forge applications for development.  Because there are quite a few (at last count 15), we'll use a simple shell loop to set them up.

    for APP in Allura* Forge* NoWarnings
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

### SOLR search and indexing server

We have a custom config ready for use.

    (anvil)~$ cd ~/src
    (anvil)~/src$ wget http://apache.mirrors.tds.net/lucene/solr/1.4.1/apache-solr-1.4.1.tgz
    (anvil)~/src$ tar xf apache-solr-1.4.1.tgz
    (anvil)~/src$ cd apache-solr-1.4.1/example/
    (anvil)~/src/apache-solr-1.4.1/example/$ mkdir -p ~/src/forge/solr_config/conf
    (anvil)~/src/apache-solr-1.4.1/example/$ cp solr/conf/solrconfig.xml ~/src/forge/solr_config/conf/
    (anvil)~/src/apache-solr-1.4.1/example/$ nohup java -Dsolr.solr.home=$(cd;pwd)/src/forge/solr_config -jar start.jar > ~/logs/solr.log &


### Forge task processing

Responds to asynchronous task requests.

    (anvil)~$ cd ~/src/forge/Allura
    (anvil)~/src/forge/Allura$ nohup paster taskd development.ini > ~/logs/taskd.log &

### TurboGears application server

In order to initialize the Forge database, you'll need to run the following:

    (anvil)~/src/forge/Allura$ paster setup-app development.ini

This shouldn't take too long, but it will start the taskd server doing tons of stuff in the background.  It should complete in 5-6 minutes.  Once this is done, you can start the application server.

    (anvil)~/src/forge/Allura$ nohup paster serve --reload development.ini > ~/logs/tg.log &

## Next Steps

Go to the server running on your [local machine](http://localhost:8080/) port 8080.
You can log in with username admin1, test-user or root.  They all have password "foo".  (For more details
on the default data, see bootstrap.py)

There are a few default projects (like "test") and neighborhoods.  Feel free to experiment with them.  If you want to
register a new project in your own forge, visit /p/add_project

## Extra

* Read more documentation: http://allura.sourceforge.net/
    * Including how to enable extra features: http://allura.sourceforge.net/installation.html
* Run the test suite (slow): `$ ALLURA_VALIDATION=none ./run_tests`
* File bug reports at <https://sourceforge.net/p/allura/tickets/new/> (login required)
* Contribute code according to this guide: <http://sourceforge.net/p/allura/wiki/Contributing%20Code/>
