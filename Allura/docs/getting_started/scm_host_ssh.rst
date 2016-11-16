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

:orphan:

.. _scm_hosting_ssh:

***************
SCM Hosting-SSH
***************

Configuring Git/SVN/Hg to use Allura auth via LDAP and ssh
==========================================================

The following instructions will use a chroot, a custom FUSE driver, and LDAP.
Once completed, an ssh-based configuration of Git, SVN, or Hg that has repos in
the chroot directory will authenticate the users against LDAP and authorize via an Allura API.
Allura will be configured to authenticate against LDAP as well.

.. note::

    The previous git & svn configuration instructions are not ssh-based, so will not work with this configuration.
    You'll have to reconfigure git & svn to use ssh:// instead of http or svn protocols.

We assume you are using a version of Ubuntu with
support for schroot and debootstrap.  We will use a chroot jail to allow users to
access their repositories via ssh.

Install a chroot environment
----------------------------

These instructions are based on the documentation in `Debootstrap Chroot`_.  and `OpenLDAPServer`_.

Install debootstrap and schroot: :program:`apt-get install debootstrap schroot`

Append the following text to the file :file:`/etc/schroot/schroot.conf`

.. code-block:: ini

    [scm]
    description=Ubuntu Chroot for SCM Hosting
    type=directory
    directory=/var/chroots/scm
    script-config=scm/config

Create a directory :file:`/etc/schroot/scm` and populate it with some files:

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

Create a directory :file:`/var/chroots/scm` and create the bootstrap environment.  (You may substitute a mirror from the  `ubuntu mirror list`_ for archive.ubuntu.com)

.. code-block:: console

    $ sudo mkdir -p /var/chroots/scm
    $ sudo debootstrap --variant=buildd --arch amd64 --components=main,universe --include=git,mercurial,subversion,openssh-server,slapd,ldap-utils,ldap-auth-client,curl maverick /var/chroots/scm http://archive.ubuntu.com/ubuntu/

Test that the chroot is installed by entering it:

.. code-block:: console

    # schroot -c scm -u root
    (scm) # logout

Configure OpenLDAP in the Chroot
--------------------------------

Copy the ldap-setup script into the chroot environment:

.. code-block:: console

    $ sudo cp Allura/ldap-setup.py Allura/ldap-userconfig.py /var/chroots/scm
    $ sudo chmod +x /var/chroots/scm/ldap-*.py

Log in to the chroot environment:

.. code-block:: console

    # schroot -c scm -u root

Run the setup script, following the prompts:

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
-----------------------------------

Update the file :file:`/var/chroot/scm/etc/ssh/sshd_config`, changing the port directive:

.. code-block:: guess

    # Port 22
    Port 8022

Setup the Custom FUSE Driver
----------------------------

Copy the accessfs script into the chroot environment:

.. code-block:: console

    $ sudo cp fuse/accessfs.py /var/chroots/scm

Configure allura to point to the chrooted scm environment:

.. code-block:: console

    $ sudo ln -s /var/chroots/scm /srv/git
    $ sudo ln -s /var/chroots/scm /srv/hg
    $ sudo ln -s /var/chroots/scm /srv/svn

Log in to the chroot environment & install packages:

.. code-block:: console

    # schroot -c scm -u root
    (scm) # apt-get install python-fuse

Create the SCM directories:

.. code-block:: console

    (scm) # mkdir /scm /scm-repo

Mount the FUSE filesystem:

.. code-block:: console

    (scm) # python /accessfs.py /scm-repo -o allow_other -s -o root=/scm

Start the SSH daemon:

.. code-block:: console

    (scm) # /etc/init.d/ssh start

Configure Allura to Use the LDAP Server
---------------------------------------

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
