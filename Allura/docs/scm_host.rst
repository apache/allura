SCM (Git, Mercurial, Subversion) Hosting Installation
==========================================================

The following instructions assume you are using a version of Ubuntu Linux with
support for schroot and debootstrap.  We will use a chroot jail to allow users to
access their repositories via ssh.

Install a chroot environment
-------------------------------------------

These instructions are based on the documentation in `Debootstrap Chroot`_.  and `OpenLDAPServer`_.

#. Install debootstrap schroot

#. Append the following text to the file /etc/schroot/schroot.conf::

    [scm]
    description=Ubuntu Chroot for SCM Hosting
    type=directory
    directory=/var/chroots/scm
    script-config=scm/config

#. Create a directory /etc/schroot/scm and populate it with some files::

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

#. Create a directory /var/chroots/scm and create the bootstrap environment.  (You may substitute a mirror from the  `ubuntu mirror list`_ for archive.ubuntu.com::

    $ sudo mkdir -p /var/chroots/scm
    $ sudo debootstrap --variant=buildd --arch amd64 --components=main,universe --include=git,mercurial,subversion,openssh-server,slapd,ldap-utils,ldap-auth-client,curl maverick /var/chroots/scm http://archive.ubuntu.com/ubuntu/

#. Test that the chroot is installed by entering it::

    # schroot -c scm -u root
    (scm) # logout

Configure OpenLDAP in the Chroot
--------------------------------------------------------------

#. Copy the ldap-setup script into the chroot environment

    $ sudo cp Allura/ldap-setup.py Allura/ldap-userconfig.py /var/chroots/scm
    $ sudo chmod +x /var/chroots/scm/ldap-*.py

#. Log in to the chroot environment:

    # schroot -c scm -u root

#. Run the setup script, following the prompts.

    (scm) # python /ldap-setup.py

In particular, you will need to anwer the following questions (substitute your custom suffix if you are not using dc=localdomain):

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

* Update the file /var/chroot/scm/etc/ssh/sshd_config, changing the port directive::

    # Port 22
    Port 8022

Setup the Custom FUSE Driver
-------------------------------------

#. Copy the accessfs script into the chroot environment

    $ sudo cp fuse/accessfs.py /var/chroots/scm

#. Configure allura to point to the chrooted scm environment

    $ sudo ln -s /var/chroots/scm /git
    $ sudo ln -s /var/chroots/scm /hg
    $ sudo ln -s /var/chroots/scm /svn

#. Log in to the chroot environment & install packages:

    # schroot -c scm -u root
    (scm) # apt-get install python-fuse

#. Create the SCM directories

    (scm) # mkdir /scm /scm-repo

#. Mount the FUSE filesystem

    (scm) # python /accessfs.py /scm-repo -o allow_other -s -o root=/scm

#. Start the SSH daemon

    (scm) # /etc/init.d/ssh start

Configure Allura to Use the LDAP Server
------------------------------------------------

Set the following values in your .ini file:

    auth.method = ldap

    auth.ldap.server = ldap://localhost
    auth.ldap.suffix = ou=people,dc=localdomain
    auth.ldap.admin_dn = cn=admin,dc=localdomain
    auth.ldap.admin_password = secret

.. _Debootstrap Chroot: https://help.ubuntu.com/community/DebootstrapChroot
.. _OpenLDAPServer: https://help.ubuntu.com/10.10/serverguide/C/openldap-server.html
.. _ubuntu mirror list: https://launchpad.net/ubuntu/+archivemirrors
