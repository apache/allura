<!--
    Licensed to the Apache Software Foundation (ASF) under one
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
-->

# Sandbox Creation

For a faster setup with a pre-packaged machine image, see [Install and Run Allura - Vagrant](https://forge-allura.apache.org/p/allura/wiki/Install%20and%20Run%20Allura%20-%20Vagrant/) instead.

In these instructions, we'll use [VirtualBox](http://www.virtualbox.org) and [Ubuntu 12.04](http://ubuntu.com) (11.10 works too) to create a disposable sandbox for Allura development/testing.  Allura should work on other Linux systems (including OSX), but setting up all the dependencies will be different.

* Download and install [VirtualBox](http://www.virtualbox.org/wiki/Downloads) for your platform.

* Download a minimal [Ubuntu 12.04 64-bit ISO](https://help.ubuntu.com/community/Installation/MinimalCD).

* Create a new virtual machine in Virtual Box, selecting Ubuntu (64 bit) as the OS type.  The rest of the wizards' defaults are fine.

* When you launch the virtual machine for the first time, you will be prompted to attach your installation media.  Browse to the `mini.iso` that you downloaded earlier.

* After a text-only installation, you may end up with a blank screen and blinking cursor.  Press Alt-F1 to switch to the first console.

* Consult [available documentation](https://help.ubuntu.com/) for help installing Ubuntu.


# Installation

Before we begin, you'll need to install some system packages.

    ~$ sudo aptitude install git-core default-jre-headless python-dev libssl-dev libldap2-dev libsasl2-dev libjpeg8-dev zlib1g-dev

To install MongoDB 2.2.3, follow the instructions here:

   <http://docs.mongodb.org/manual/tutorial/install-mongodb-on-ubuntu/>

Optional, for SVN support:

    ~$ sudo aptitude install subversion python-svn

## Setting up a virtual python environment

The first step to installing the Allura platform is installing a virtual environment via `virtualenv`.  This helps keep our distribution python installation clean.

    ~$ sudo aptitude install python-pip
    ~$ sudo pip install virtualenv

Once you have virtualenv installed, you need to create a virtual environment.  We'll call our Allura environment 'env-allura'.

    ~$ virtualenv env-allura

This gives us a nice, clean environment into which we can install all the allura dependencies.
In order to use the virtual environment, you'll need to activate it:

    ~$ . env-allura/bin/activate

You'll need to do this whenever you're working on the Allura codebase so you may want to consider adding it to your `~/.bashrc` file.

## Installing the Allura code and dependencies

Now we can get down to actually getting the Allura code and dependencies downloaded and ready to go.  If you don't have the source code yet, run:

    (env-allura)~$ mkdir src
    (env-allura)~$ cd src
    (env-allura)~/src$ git clone https://git-wip-us.apache.org/repos/asf/incubator-allura.git allura

If you already reading this file from an Allura release or checkout, you're ready to continue.

Although the application setup.py files define a number of dependencies, the `requirements.txt` files are currently the authoritative source, so we'll use those with `pip` to make sure the correct versions are installed.

    (env-allura)~/src$ cd allura
    (env-allura)~/src/allura$ pip install -r requirements.txt

This will take a while.  If you get an error from pip, it is typically a temporary download error.  Just run the command again and it will quickly pass through the packages it already downloaded and then continue.

Optional, for SVN support: symlink the system pysvn package into our virtual environment

    (env-allura)~/src/allura$ ln -s /usr/lib/python2.7/dist-packages/pysvn ~/env-allura/lib/python2.7/site-packages/

And now to setup the Allura applications for development.  If you want to setup all of them, run `./rebuild-all.bash`
If you only want to use a few tools, run:

    cd Allura
    python setup.py develop
    cd ../ForgeWiki   # required tool
    python setup.py develop
    # repeat for any other tools you want to use

## Initializing the environment

The Allura forge consists of several components, all of which need to be running to have full functionality.

### SOLR search and indexing server

We have a custom config ready for use.

    (env-allura)~$ cd ~/src
    (env-allura)~/src$ wget -nv http://archive.apache.org/dist/lucene/solr/4.2.1/solr-4.2.1.tgz
    (env-allura)~/src$ tar xf solr-4.2.1.tgz && rm -f solr-4.2.1.tgz
    (env-allura)~/src$ cp -f allura/solr_config/schema.xml solr-4.2.1/example/solr/collection1/conf

    (env-allura)~/src$ cd solr-4.2.1/example/
    (env-allura)~/src/apache-solr-4.2.1/example/$ mkdir ~/logs/
    (env-allura)~/src/apache-solr-4.2.1/example/$ nohup java -jar start.jar > ~/logs/solr.log &


### Allura task processing

Allura uses a background task service called "taskd" to do async tasks like sending emails, and indexing data into solr, etc.  Let's get it running

    (env-allura)~$ cd ~/src/allura/Allura
    (env-allura)~/src/allura/Allura$ nohup paster taskd development.ini > ~/logs/taskd.log &

### The application server

In order to initialize the Allura database, you'll need to run the following:

    (env-allura)~/src/allura/Allura$ paster setup-app development.ini

This shouldn't take too long, but it will start the taskd server doing tons of stuff in the background.  Once this is done, you can start the application server:

    (env-allura)~/src/allura/Allura$ nohup paster serve --reload development.ini > ~/logs/tg.log &

## Next Steps

Go to the Allura webapp running on your [local machine](http://localhost:8080/) port 8080.
(If you're running this inside a VM, you'll probably have to configure the port forwarding settings)

You can log in with username admin1, test-user or root.  They all have password "foo".  (For more details
on the default data, see bootstrap.py)

There are a few default projects (like "test") and neighborhoods.  Feel free to experiment with them.  If you want to
register a new project in your own forge, visit /p/add_project

## Extra

* Read more documentation: <http://allura.sourceforge.net/docs/>
    * Including how to enable extra features: <http://allura.sourceforge.net/docs/installation.html>
* Run the test suite (slow): `$ ALLURA_VALIDATION=none ./run_tests`
* File bug reports at <https://sourceforge.net/p/allura/tickets/new/> (login required)
* Contribute code according to this guide: <https://forge-allura.apache.org/p/allura/wiki/Contributing%20Code/>
