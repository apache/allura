Mac OSX: supplemental install directions
========================================

This supplements OpenForge's `Getting Started Guide`_. Please refer to that document first.

.. _`Getting Started Guide`: install.html
.. _`Mac Ports`: http://www.macports.org/

Following this guide will install the required dependencies to run the forge 
on your Mac. These instructions have been tested on Snow Leopard but should 
work on Leopard also, please update them as needed. It's recommended that you 
execute the following instructions one at a time, and verify each works. 
The instructions assume you already have `Mac Ports`_ installed::

    $ sudo port install git-core +bash_completion # pulls in perl, may take a while
    $ sudo port install python26 +no_tkinter # trying to avoid pulling in tk, xorg, et al.
    $ sudo port install py26-pil # make sure we have all the right deps, and can use directly if we didn't do --no-site-packages in our virtualenv
    $ sudo port install py26-virtualenv # after this we'll install all python modules with virtualenv, not macports
    $ sudo port install subversion +bash_completion
    $ sudo port install mongodb # it builds with scons (requires py26) so do it after we install python26 w/ variant
    $ mkdir -p /data/db # make a data directory for mongo
    $ sudo port install tidy
    $ sudo port install wget
    $ sudo port install erlang
    $ sudo port install rabbitmq-server

.. sidebar:: RabbitMQ LaunchCtl possible problems and work-around

    Note: rabbitmq's startup/LaunchCtl didn't work on Andy's Snow Leopard OS. 
    Specifically, erlang errors regarding an error like 
    'Protocol: ~p: register error: ~p~n",["inet_tcp", ...'. He runs it 
    manually from a new terminal window instead, e.g. sudo rabbitmq-server

.. _SOLR: http://lucene.apache.org/solr/

Install SOLR_ from source. Following copied from setup-local.bash::

    $ mkdir -p ~/src
    $ cd ~/src
    $ wget http://apache.mirrors.tds.net/lucene/solr/1.4.0/apache-solr-1.4.0.tgz
    $ tar xzf apache-solr-1.4.0.tgz
    $ # in the Getting Started Doc, <path_to_solr> will be ~/src/apache-solr-1.4.0

Setup a virtual env. Feel free to substitue forge_env for something of your preference::

    $ cd /opt/local/bin
    $ sudo ln -s easy_install-2.6 easy_install
    $ sudo ln -s ipython2.6 ipython
    $ sudo ln -s virtualenv2.6 virtualenv
    $ mkdir -p ~/dev
    $ cd !$
    $ virtualenv --no-site-packages forge_env
    $ . forge_env/bin/activate
    (forge-env)$ easy_install --find-links http://www.pythonware.com/products/pil/ Imaging
    (forge-env)$ easy_install ipython # make sure you're within the virtual env, so ipython will have all the local env packages

At this point, go back to `Getting Started Guide`_. You have already installed 
virtualenv and activated it, and are ready to install turbogears.

Note: Some developers are having success running mongo, rabbit, solr, forge's smtp_server, 
reactor and the forge in their separate terminal windows. So to start the forge after a 
reboot, Andy opens a new Terminal window for each and startup each service following 
the instructions in the `Getting Started Guide`_ for that service.
