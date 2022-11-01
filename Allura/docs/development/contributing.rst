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

.. _contributing:

************
Contributing
************

Contributing to Allura
======================
For developers interested in hacking on Allura or its components, this guide
will (hopefully) be a roadmap to help you get started and guide you on your
way.

Getting Help
------------
Along the way, you will no doubt have questions that aren't addressed here.
For help, you can get in touch with other Allura developers on the developer
mailing list (dev@allura.apache.org) or in the #allura channel on
the Freenode IRC network.

Installing Allura
-----------------
Before hacking on Allura, you'll need to get an Allura instance up and running
so you can see and test the changes you make. You can install Allura from
scratch, or by using our Docker container images. Instructions for these
approaches can be found here:

* :ref:`Install from scratch <step-by-step-install>`
* :ref:`Install using Docker <docker-install>`

Managing Services
-----------------
Allura is comprised of a handful of separate services, all of which must be
running in order for the system to be fully functional. These services (and
how to start them) are covered in the install documentation, but are mentioned
again here simply to reiterate the components of a complete Allura system.

External services:

* MongoDB - database
* Solr - searching/indexing

Allura services:

* Web server - the Allura web application
* :doc:`Taskd <../platform/message_bus>` - background task daemon
* Inbound email handler - processes email sent to the Allura instance (e.g.,
  a reply to a ticket notification email)

Logging
-------
The logs for Allura services can be found in ``/var/log/allura/``.
The most important of these is ``allura.log``, as it will contain log messages
for all Allura application code.

Technology Stack
----------------
`MongoDB <http://www.mongodb.org/>`_ - Allura stores all of its data in MongoDB.
If you're new to MongoDB, you'll want to keep the `reference docs
<http://docs.mongodb.org/manual/reference/>`_ handy until you're familiar with
basic query operations and syntax.

`Solr <http://lucene.apache.org/solr/>`_ - Allura artifact data is indexed into
Solr so that it can be searched. In general, you won't need to know much about
Solr in order to work on Allura.

`Turbogears <http://turbogears.org/>`_ - Allura is built on the TurboGears web
framework. Understanding `TG controller basics <http://turbogears.readthedocs.org/en/tg2.3.0b2/turbogears/controllers.html>`_
and `object dispatch <http://turbogears.readthedocs.org/en/tg2.3.0b2/turbogears/objectdispatch.html>`_,
TurboGears' mechanism for routing an HTTP request to the code that should handle
it, are critical for understanding how a request is handled by Allura.

`Ming <http://merciless.sourceforge.net/index.html>`_ - Allura interfaces with
MongoDB through Ming, a library which provides an Object Document Mapper for
MongoDB. Fortunately, the query syntax is mostly identical to that of
native MongoDB, so the learning curve is pretty flat.

`EasyWidgets <http://easywidgets.pythonisito.com/index.html>`_ - An HTML template
and form validation library used by Allura. The learning curve on EasyWidgets
is, ironically, not easy. Be prepared to dig into the source if you want to
do something complicated with EW. Fortunately, there are lots of exmaples in
the Allura source already.

`Jinja <http://jinja.pocoo.org/>`_ - HTML template library used by Allura.

If you want to work on the front end of Allura, you'll also need some CSS and
Javascript skills, and basic knowledge of JQuery.  We are also using React and ES6.
To transpile those files as soon as you edit them:

.. code-block:: bash

    ~$ cd ~/src/allura
    ~$ npm run watch


Finding Something to Work On
----------------------------
Tickets that are relatively simple and good for new contributors have a
"bitesize" label, and can be found here:
https://forge-allura.apache.org/p/allura/tickets/search/?q=labels%3Abitesize+AND+status%3Aopen

Find one that looks good, and leave a comment on the ticket or mailing list
to let us know you're working on it. If you get stuck, remember that we're
available to help on the mailing list or IRC.

Code Organization
-----------------
The core Allura platform code is in the ``Allura/`` directory in the top-level of the
repo. The ``Forge*/`` directories contain Allura "tools" - plugins that extend the
core platform. For an overview of the platform and services it provides, read
the :doc:`Platform Tour <../platform/platform_tour>` documentation. If you're interested in
developing a new Allura plugin, you may find this `blog series <https://sourceforge.net/u/vansteenburgh/allura-plugin-development/>`_
helpful.

Tracing a Request
-----------------
Whether you're fixing a bug or adding a new feature, one of your first
questions will be, "Where is the code that is handling this request (or serving
this page)?" For a new contributor, answering this question can be surprisingly
challenging. Here are some tips to help you out:

1. The root controller for the entire application is in
``Allura/allura/controllers/root.py`` - dispatch for *every* request begins
here. It is possible (albeit difficult) to trace the path your request
will take through the code from this starting point if you have a
thorough knowledge of Turbogears' request dispatch mechanics. But, nobody
wants to do this if they can avoid it.

2. Is the page being served part of a tool (e.g. Ticket Tracker, Wiki, etc)?
Most of the time, the answer is yes. If you know which tool is handling the
request, you can skip right to the root controller for that tool. To find the
root controller, first find the main entry point for the tool, which is defined
in the ``[allura]`` section of the tool's  ``setup.py`` file. So, for example,
if you know the request is being handled by a Ticket Tracker, look in
``ForgeTracker/setup.py`` and you'll see that that its entry point is
``forgetracker.tracker_main:ForgeTrackerApp``. Each Allura tool instance
defines a ``root`` attribute which is its root controller. So once you've found
the main tool class, you can find its root controller and begin tracing your
request from there.

3. Search for things! ``grep`` and equivalents are your friends. If you're
looking at an html page and want to find the controller code for it, try
searching the code base for some (static) text on the page. If your search
successfully turns up an html page, search again on the name of the html file.
There's a good change you'll find the controller method that renders that page.

Interactive Debugging
---------------------
If you've never used ``ipdb`` before, you'll find it's a great tool for
interactive debugging of Python code. In order to use ``ipdb`` to debug Allura,
you'll first need to make sure that the process you're debugging is running in
the foreground. In most cases you'll be debugging either the web app process
or the taskd (background worker) process.

First, make sure sure ipdb is installed in your virtual environment::

    pip install ipdb

Then, find the line of code where you want to start the interactive debugger,
and insert this line above it::

    import ipdb; ipdb.set_trace()

Now, kill any running web or taskd procs and restart them in the
foreground::

    cd Allura
    # web
    pkill -f gunicorn; gunicorn --reload --paste development.ini -b :8080
    # taskd
    pkill "^taskd"; paster taskd development.ini --nocapture

Then make a request to the web app, and when your line of code is hit, a debug
session will start on the console where the process is running.

For more information about using ``pdb``, see the `official documentation
<http://docs.python.org/2/library/pdb.html>`_.  ``ipdb`` is version of ``pdb`` with
support for IPython's tab completion, syntax highlighting etc.  Other debugger packages such
as ``pudb`` are also available.

.. note::

   To do this with docker, the commands are::

       docker-compose run web pip install ipdb
       docker-compose stop web taskd
       docker-compose run --service-ports web gunicorn --reload --paste Allura/docker-dev.ini -b :8088
       docker-compose run taskd paster taskd docker-dev.ini --nocapture


Testing
-------
To run all the tests, execute ``./run_tests`` in the repo root. To run tests
for a single package, for example ``forgetracker``::

  cd ForgeTracker && pytest

To learn more about the ``pytest`` test runner, consult the `documentation
<https://docs.pytest.org/en/latest/contents.html>`_.

When writing code for Allura, don't forget that you'll need to also create
tests that cover behaviour that you've added or changed. You may find this
:doc:`short guide <../development/testing>` helpful.


Submitting a Merge Request
--------------------------
Before submitting a merge request, make sure your changes conform to our
`contribution guidelines <https://forge-allura.apache.org/p/allura/wiki/Contributing%20Code/>`_.
Once your changes are finished and tested, submit them to be merged back into
the main repo:

* Fork the main Allura repo from here: https://forge-allura.apache.org/p/allura/git/
* Commit and push your changes to your fork
* Submit a Merge Request from your fork
