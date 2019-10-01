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

.. _scm_hosting:

**************
SCM Host Setup
**************


Git and Subversion Hosting Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Allura can manage and display Git and SVN repositories, but it doesn't
automatically run the git and svn services for you.  Here we'll describe how
to set up standard git and svn services to work with Allura, so that you can
checkout and commit code with those repositories.  The instructions here assume
an Ubuntu system, but should be similar on other systems.

.. note::

    For developing with Allura or simple testing of Allura, you do not need to run
    these services.  You can use local filesystem access to git and svn, which
    works with no additional configuration.

Git
---

We'll cover the basics to get you going.  For additional options and details,
see http://git-scm.com/docs/git-http-backend and http://git-scm.com/book/en/Git-on-the-Server
and subsequent chapters.

.. code-block:: bash

    sudo chmod 775 /srv/*  # make sure apache can read the repo dirs
    sudo apt-get install apache2
    sudo a2enmod cgi
    # allow the apache user to sudo (used by git-http-backend-wrapper.sh see notes in that file)
    sudo adduser www-data sudo
    sudo echo '%sudo  ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sudo_group_passwordless

    sudo vi /etc/apache2/sites-available/default

And add the following text within the :code:`<VirtualHost>` block:

.. code-block:: apache

    SetEnv GIT_PROJECT_ROOT /srv/git
    SetEnv GIT_HTTP_EXPORT_ALL
    ScriptAlias /git/ /usr/lib/git-core/git-http-backend-wrapper.sh/

    # no authentication required at all - for testing purposes
    SetEnv REMOTE_USER=git-allura
    <Location "/git/">
        # new for httpd 2.4
        Require all granted
    </Location>

Then exit vim (:kbd:`<esc> :wq`) and run:

.. code-block:: shell-session

    sudo service apache2 reload

To test that it's working, run: :command:`git ls-remote http://localhost/git/p/test/git/`.
If there is no output, that is fine (it's an empty repo).

.. warning::

    This configuration has no authentication and is suitable for development only.  See :ref:`below <auth_apache>` for auth config.

Now you will want to change the :samp:`scm.host.{*}.git` and :samp:`scm.clonechoices.git`
settings in :file:`development.ini`, so that the proper commands are shown to your visitors
when they browse the code repo web pages.  The exact values to use will depend on the
hostnames and port numbers you are using.

Read-only `git://`
^^^^^^^^^^^^^^^^^^
If you want to run a separate readonly git service, using the git protocol instead of http,
run: :program:`git daemon --reuseaddr --export-all --base-path=/srv/git /srv/git`  It can
be accessed at :code:`git://localhost/p/test/git`


Subversion
----------

These instructions will cover the recommended easiest way to run Subversion with Allura.
For an overview of other options, see http://svnbook.red-bean.com/en/1.8/svn.serverconfig.choosing.html
and subsequent chapters.

.. code-block:: bash

    sudo chown allura:allura /srv/svn  # or other user, as needed

    cat > /srv/svn/svnserve.conf <<EOF
    [general]
    realm = My Site SVN
    # no authentication required at all - for testing purposes
    anon-access = write
    EOF

    svnserve -d -r /srv/svn --log-file /tmp/svnserve.log --config-file /srv/svn/svnserve.conf

Test by running: :command:`svn info svn://localhost/p/test/code/`.  If you need to kill it,
run :command:`killall svnserve`  More info at http://svnbook.red-bean.com/en/1.8/svn.serverconfig.svnserve.html

.. warning::

    This configuration has no authentication and is suitable for development only.
    (Maybe Allura could gain SASL support someday and use `svnserve with SASL <http://svnbook.red-bean.com/en/1.7/svn.serverconfig.svnserve.html#svn.serverconfig.svnserve.sasl>`_)

Now you will want to change the :samp:`scm.host.{*}.svn` and :samp:`scm.clonechoices.svn`
settings in :file:`development.ini`, so that the proper commands are shown to your visitors
when they browse the code repo web pages.

Alternate Setup with HTTP
^^^^^^^^^^^^^^^^^^^^^^^^^

To use SVN over HTTP, you will need to patch and compile an Apache module, so
that all svn repos can be dynamically served.

.. warning::

    Not easy.

.. code-block:: console

    sudo apt-get install libapache2-svn

Test accessing http://localhost/.

Now we'll configure Apache to serve a single project's repositories and make sure
that works.

.. code-block:: console

    sudo vi /etc/apache2/mods-available/dav_svn.conf

Uncomment and change to :code:`<Location /svn/p/test>`.  Set
:code:`SVNParentPath /srv/svn/p/test`  Then run:

.. code-block:: console

    sudo service apache2 reload

Test at http://localhost/svn/p/test/code/

That configuration works only for the repositories in a single project.  You must either
create a new configuration for each project within Allura, or compile a patch
to make `SVNParentPath` be recursive.  The patch is at https://issues.apache.org/jira/browse/SVN-3588
and must be applied to the source of Subversion's mod_dav_svn and then
recompiled and installed.  Once that is working, you can modify :file:`dav_svn.conf` to look like:

.. code-block:: apache

    <Location /svn>
      DAV svn
      SVNParentPath /srv/svn
      ...

Then Apache SVN will serve repositories for all Allura projects and subprojects.

.. warning::

    This configuration has no authentication and is suitable for development only.  See :ref:`the next section <auth_apache>` for auth config.


.. _auth_apache:

Configuring Auth with Apache
----------------------------

This is the easiest way to integrate authentication and authorization for SCM access with Allura.  It uses
mod_python and the handler in :file:`scripts/ApacheAccessHandler.py` to query Allura directly
for auth and permissions before allowing access to the SCM.  Of course, this only works
for SCM access over HTTP(S).

First, you need to ensure that mod_python is installed:

.. code-block:: console

    sudo apt-get install libapache2-mod-python

Then, in the VirtualHost section where you send SCM requests to git, SVN, or Hg, add the
access handler, e.g.:

.. code-block:: console

    sudo vi /etc/apache2/sites-available/default

Remove the `<Location>` block and `SetEnv REMOTE_USER=git-allura` from earlier.

.. code-block:: apache

    <LocationMatch "^/(git|svn|hg)/">
        # new for httpd 2.4
        Require all granted

        AddHandler mod_python .py
        # Change this path if needed:
        PythonAccessHandler /home/myuser/src/allura/scripts/ApacheAccessHandler.py

        AuthType Basic
        AuthName "SCM Access"
        AuthBasicAuthoritative off

        # Change this path if needed:
        PythonOption ALLURA_VIRTUALENV /home/myuser/env-allura
        # This routes back to the allura webapp
        # In a production environment, change the IP address and port number as appropriate.
        # And use https if possible, since the username and password are otherwise
        # sent in the clear to Allura.
        PythonOption ALLURA_AUTH_URL http://127.0.0.1:8080/auth/do_login
        PythonOption ALLURA_PERM_URL http://127.0.0.1:8080/auth/repo_permissions
    </LocationMatch>

.. code-block:: console

    sudo service apache2 reload

To test that it's working, run: :command:`git ls-remote
http://localhost/git/p/test/git/`. If there is no output, that is fine (it's an empty
repo). If it errors, look in :file:`/var/log/apache2/error.log` for the error
message.  Increase logging with the `LogLevel <https://httpd.apache.org/docs/2.4/mod/core.html#loglevel>`_ directive
if needed for further debugging.

.. warning::

    Currently, for Mercurial, the handler doesn't correctly distinguish read
    and write requests and thus requires WRITE permission for every request.
    See ticket #7288

.. note::

    If two-factor auth is enabled, enter your password + current 6-digit code together, as your password.
    You will have to enter your password each time, and may run into temporary permission denied when it fails.


Advanced Alternative
--------------------

An advanced alternative for SCM hosting using :ref:`SSH, LDAP, and a FUSE driver <scm_hosting_ssh>` is available.