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

Git and Subversion Hosting Installation
==========================================================

Allura can manage and display Git and SVN repositories, but it doesn't
automatically run the git and svn services for you.  Here we'll describe how
to set up standard git and svn services to work with Allura, so that you can
checkout and commit code with those repositories.

Git
--------------

We'll cover the basics to get you going.  For additional options and details,
see http://git-scm.com/docs/git-http-backend and http://git-scm.com/book/en/Git-on-the-Server
and subsequent chapters.  The instructions here assume an
Ubuntu system, but should be similar on other systems.

.. code-block:: console

    sudo a2enmod proxy rewrite
    sudo vi /etc/apache2/sites-available/default

And add the following text within the `<VirtualHost>` block:

.. code-block:: apache

    SetEnv GIT_PROJECT_ROOT /srv/git
    SetEnv GIT_HTTP_EXPORT_ALL
    ProxyPass /git/ !
    ScriptAlias /git/ /usr/lib/git-core/git-http-backend/

    RewriteCond %{QUERY_STRING} service=git-receive-pack [OR]
    RewriteCond %{REQUEST_URI} /git-receive-pack$
    RewriteRule ^/git/ - [E=AUTHREQUIRED:yes]

    <LocationMatch "^/git/">
        Order Deny,Allow
        Deny from env=AUTHREQUIRED

        AuthType Basic
        AuthName "Git Access"
        Require group committers
        Satisfy Any
    </LocationMatch>

Then exit vim (`<esc> :wq`) and run:

.. code-block:: shell-session

    sudo service apache2 reload

To test that it's working, run: `git ls-remote http://localhost/git/p/test/git/`
(if using vagrant, use localhost:8088 on your host machine).  If there is no output,
that is fine (it'll list git heads once the repo has commits in it).

Note that this has no authentication and is suitable for development only.

If you want to run a separate readonly git service, using the git protocol instead of http,
run: `git daemon --reuseaddr --export-all --base-path=/srv/git /srv/git`  It can
be accessed at `git://localhost/p/test/git`

Depending on the hostname and ports you use, you may need to change the `scm.host.*`
settings in `development.ini`.


Subversion
--------------


Temp Notes:
--------------


STRUCTURE:
separate authentication (ldap, allura) vs authorization (via allura API)
different protocol (svn:// & git:// vs http)
    http://svnbook.red-bean.com/en/1.8/svn.serverconfig.choosing.html
    http://git-scm.com/book/ch4-1.html

TODO:
    disable scm.host.https* in .ini?
    remove /home/vagrant/scm/ symlinks?

SVN
    `sudo aptitude install libapache2-svn`
    test http://localhost:80/ (8088 if vagrant)
    `vi /etc/apache2/mods-available/dav_svn.conf`
        uncomment things
        Have to do a location & parentpath for each project, e.g "test" project
        <Location /svn/p/test>
        SVNParentPath /srv/svn/p/test
        todo: Auth* directives
    `service apache2 reload`
    test http://localhost:80/svn/p/test/code/ (8088 if vagrant)
    Now can change scm.host.(https|https_anon).svn to "http://localhost:80/svn$path/" (8088 if vagrant) for checkout instructions
        scm.host.(ro|rw) are intended for svn:// protocol
    make SVNParentPath recursive:
        http://subversion.tigris.org/issues/show_bug.cgi?id=3588
        https://sourceforge.net/p/allura/pastebin/517557273e5e837ec65122c1
        latest: https://trac.sdot.me/git/?p=srpmtree.git;a=blob_plain;f=subversion-recursive-parentpath.patch;hb=refs/heads/sog/subversion
        need to update it for trunk/1.8.x
        http://subversion.apache.org/docs/community-guide/general.html#patches
        http://subversion.apache.org/docs/community-guide/conventions.html

    svnserve shouldn't have parentpath restrictions, it allows complete access to a dir
        svnserve -d -r /srv/svn -R
        test: svn info svn://localhost/p/test/code/
        killall svnserve
        more info: http://svnbook.red-bean.com/en/1.8/svn.serverconfig.svnserve.html


~~~~~~~

The following instructions assume you are using a version of Ubuntu Linux with
support for schroot and debootstrap.  We will use a chroot jail to allow users to
access their repositories via ssh.

Install a chroot environment
-------------------------------------------

These instructions are based on the documentation in `Debootstrap Chroot`_.  and `OpenLDAPServer`_.

#. Install debootstrap schroot

#. Append the following text to the file /etc/schroot/schroot.conf

.. code-block:: ini

    [scm]
    description=Ubuntu Chroot for SCM Hosting
    type=directory
    directory=/var/chroots/scm
    script-config=scm/config

#. Create a directory /etc/schroot/scm and populate it with some files:

.. code-block:: console

    # mkdir /etc/schroot/scm
    # cat > /etc/schroot/scm/config <<EOF
    FSTAB="/etc/schroot/scm/fstab"
    COPYFILES="/etc/schroot/scm/copyfiles"
    NSSDATABASES="/etc/schroot/scm/nssdatabases"
    EOF
    # cat > /etc/schroot/scm/fstab <<EOF
    /proc		/proc		none    rw,rbind        0       0
    /sys		/sys		none    rw,rbind        0       0
    /dev            /dev            none    rw,rbind        0       0
    /tmp		/tmp		none	rw,bind		0	0
    EOF
    # cat > /etc/schroot/scm/copyfiles <<EOF
    /etc/resolv.conf
    EOF
    # cat > /etc/schroot/scm/nssdatabases <<EOF
    services
    protocols
    networks
    hosts
    EOF

#. Create a directory /var/chroots/scm and create the bootstrap environment.  (You may substitute a mirror from the  `ubuntu mirror list`_ for archive.ubuntu.com)

.. code-block:: console

    $ sudo mkdir -p /var/chroots/scm
    $ sudo debootstrap --variant=buildd --arch amd64 --components=main,universe --include=git,mercurial,subversion,openssh-server,slapd,ldap-utils,ldap-auth-client,curl maverick /var/chroots/scm http://archive.ubuntu.com/ubuntu/

#. Test that the chroot is installed by entering it:

.. code-block:: console

    # schroot -c scm -u root
    (scm) # logout

Configure OpenLDAP in the Chroot
--------------------------------------------------------------

#. Copy the ldap-setup script into the chroot environment:

.. code-block:: console

    $ sudo cp Allura/ldap-setup.py Allura/ldap-userconfig.py /var/chroots/scm
    $ sudo chmod +x /var/chroots/scm/ldap-*.py

#. Log in to the chroot environment:

.. code-block:: console

    # schroot -c scm -u root

#. Run the setup script, following the prompts:

.. code-block:: console

    (scm) # python /ldap-setup.py

In particular, you will need to answer the following questions (substitute your custom suffix if you are not using dc=localdomain):

* Should debconf manage LDAP configuration? **yes**
* LDAP server Uniform Resource Identifier: **ldapi:///**
* Distinguished name of the search base: **dc=localdomain**
* LDAP version to use: **1** (version 3)
* Make local root Database admin: **yes**
* Does the LDAP database require login? **no**
* LDAP account for root: **cn=admin,dc=localdomain**
* LDAP root account password: *empty*
* Local crypt to use when changing passwords: **2** (crypt)
* PAM profiles to enable: **2**

Update the chroot ssh configuration
-------------------------------------------------

* Update the file /var/chroot/scm/etc/ssh/sshd_config, changing the port directive:

.. code-block:: guess

    # Port 22
    Port 8022

Setup the Custom FUSE Driver
-------------------------------------

#. Copy the accessfs script into the chroot environment:

.. code-block:: console

    $ sudo cp fuse/accessfs.py /var/chroots/scm

#. Configure allura to point to the chrooted scm environment:

.. code-block:: console

    $ sudo ln -s /var/chroots/scm /git
    $ sudo ln -s /var/chroots/scm /hg
    $ sudo ln -s /var/chroots/scm /svn

#. Log in to the chroot environment & install packages:

.. code-block:: console

    # schroot -c scm -u root
    (scm) # apt-get install python-fuse

#. Create the SCM directories:

.. code-block:: console

    (scm) # mkdir /scm /scm-repo

#. Mount the FUSE filesystem:

.. code-block:: console

    (scm) # python /accessfs.py /scm-repo -o allow_other -s -o root=/scm

#. Start the SSH daemon:

.. code-block:: console

    (scm) # /etc/init.d/ssh start

Configure Allura to Use the LDAP Server
------------------------------------------------

Set the following values in your .ini file:

.. code-block:: ini

    auth.method = ldap

    auth.ldap.server = ldap://localhost
    auth.ldap.suffix = ou=people,dc=localdomain
    auth.ldap.admin_dn = cn=admin,dc=localdomain
    auth.ldap.admin_password = secret

.. _Debootstrap Chroot: https://help.ubuntu.com/community/DebootstrapChroot
.. _OpenLDAPServer: https://help.ubuntu.com/10.10/serverguide/C/openldap-server.html
.. _ubuntu mirror list: https://launchpad.net/ubuntu/+archivemirrors
