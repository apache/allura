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

**************
Administration
**************

.. contents::
   :local:

Commands, Scripts, and Tasks
============================

Overview
--------

Allura has many commands and scripts that can be run from the server commandline to
administrate Allura.  There are also tasks that can be run through the `taskd` system
in the background.  These tasks can be submitted via the web at
http://MYSITE/nf/admin/task_manager  Some paster scripts have been set up
so that they are runnable as tasks too, giving you the convenience of starting
them through the web and letting `taskd` execute them, rather than from a server
shell.

Commands can be discovered and run via the `paster` command when you are in the
'Allura' directory that has your .ini file.  For example::

     paster help
    ... all commands listed here ...

     paster create-neighborhood --help
    ... specific command help ...

     paster create-neighborhood development.ini myneighborhood myuser ...


Scripts are in the `scripts/` directory and run slightly differently, via `paster script`.  An extra
:kbd:`--` is required to separate script arguments from paster arguments.  Example::

     paster script development.ini ../scripts/create-allura-sitemap.py -- --help
    ... help output ...

     paster script development.ini ../scripts/create-allura-sitemap.py -- -u 100

Tasks can be run via the web interface at http://MYSITE/nf/admin/task_manager  You must know
the full task name, e.g. :code:`allura.tasks.admin_tasks.install_app`  You can
optionally provide a username and project and app which will get set on the
current context (`c`).  You should specify what args and kwargs will be passed
as parameters to the task.  They are specified in JSON format on the form.  If you are
running a script via this interface, the `args/kwargs` JSON should be like::

    {
        "args": ["--foo --bar baz"],
        "kwargs": {}
    }

See the listing of :mod:`some available tasks <allura.tasks.admin_tasks>`.

Available scripts and tasks are:

disable_users.py
----------------

*Can be run as a background task using task name:* :code:`allura.scripts.disable_users.DisableUsers`

.. argparse::
    :module: allura.scripts.disable_users
    :func: get_parser
    :prog: paster script development.ini allura/scripts/disable_users.py --

refreshrepo.py
--------------

*Can be run as a background task using task name:* :code:`allura.scripts.refreshrepo.RefreshRepo`

.. argparse::
    :module: allura.scripts.refreshrepo
    :func: get_parser
    :prog: paster script development.ini allura/scripts/refreshrepo.py --

reindex_projects.py
-------------------

*Can be run as a background task using task name:* :code:`allura.scripts.reindex_projects.ReindexProjects`

.. argparse::
    :module: allura.scripts.reindex_projects
    :func: get_parser
    :prog: paster script development.ini allura/scripts/reindex_projects.py --

reindex_users.py
----------------

*Can be run as a background task using task name:* :code:`allura.scripts.reindex_users.ReindexUsers`

.. argparse::
    :module: allura.scripts.reindex_users
    :func: get_parser
    :prog: paster script development.ini allura/scripts/reindex_users.py --

create-allura-sitemap.py
------------------------

*Cannot currently be run as a background task.*

.. argparse::
    :file: ../../scripts/create-allura-sitemap.py
    :func: parser
    :prog: paster script development.ini ../scripts/create-allura-sitemap.py --

publicize-neighborhood.py
-------------------------

*Cannot currently be run as a background task.*

.. argparse::
    :file: ../../scripts/publicize-neighborhood.py
    :func: parser
    :prog: paster script development.ini ../scripts/publicize-neighborhood.py --

scrub-allura-data.py
--------------------

*Cannot currently be run as a background task.*

.. argparse::
    :file: ../../scripts/scrub-allura-data.py
    :func: parser
    :prog: paster script development.ini ../scripts/scrub-allura-data.py --

teamforge-import.py
-------------------

*Cannot currently be run as a background task.*

Extract data from a TeamForge site (via its web API), and import directly into Allura.  There are some hard-coded
and extra functions in this script, which should be removed or updated before being used again.
Requires running: :command:`pip install suds` first. ::

    usage: paster script development.ini ../scripts/teamforge-import.py -- --help



Client Scripts
==============

Allura includes some client scripts that use Allura APIs and do not have to be run
from an Allura server.  They do require various python packages to be installed
and possibly a local Allura codebase set up.

One such script is `wiki-copy.py` which reads the wiki pages from one Allura wiki
instance and uploads them to another Allura wiki instance.  It can be run as:

.. code-block:: console

    $ python scripts/wiki-copy.py --help


Site Notifications
==================

Allura has support for site-wide notifications that appear below the site header,
but there is currently no UI for managing them.  They can easily be inserted via
manual mongo queries, however:

.. code-block:: console

    > db.site_notification.insert({
    ... active: true,
    ... impressions: 10,
    ... content: 'You can now reimport exported project data.'
    ... })

This will create a notification that will be shown for 10 page views or until the
user closes it manually.  An `impressions` value of 0 will show the notification
indefinitely (until closed).  The notification content can contain HTML.  Only the
most recent notification will be shown, unless it has `active:false`, in which case
no notification will be shown.


Using Projects and Tools
========================

We currently don't have any further documentation for basic operations of managing
users, projects, and tools on Allura.  However, SourceForge has help docs that cover
these functions https://sourceforge.net/p/forge/documentation/Docs%20Home/  Note
that this documentation also covers some SourceForge features that are not part of Allura.

.. _public_api:

Public API Documentation
========================

Allura's web api is currently documented at https://sourceforge.net/p/forge/documentation/Allura%20API/
