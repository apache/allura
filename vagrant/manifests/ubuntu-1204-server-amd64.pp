#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

# create puppet group
group { "puppet":
  ensure => "present",
}

exec { "package index update":
    command => "/usr/bin/apt-get update",
}

# install required system packages
Package { ensure => "installed" }

$packages = [
 "git-core",
 "subversion",
 "python-svn",
 "default-jre-headless",
 "python-dev",
 "libssl-dev",
 "libldap2-dev",
 "libsasl2-dev",
 "libjpeg8-dev",
 "zlib1g-dev",
 "python-pip"
]

package { $packages:
    require => Exec[ "package index update" ],
}

file { '/usr/lib/libz.so':
  ensure => 'link',
  target => '/usr/lib/x86_64-linux-gnu/libz.so',
  require => Package[ "zlib1g-dev" ],
}
file { '/usr/lib/libjpeg.so':
  ensure => 'link',
  target => '/usr/lib/x86_64-linux-gnu/libjpeg.so',
  require => Package[ "libjpeg8-dev" ],
}

# install python pip
exec { "install venv":
  command => "/usr/bin/pip install virtualenv",
  creates => "/usr/local/bin/virtualenv",
  require => Package[ "python-pip" ],
}

# create Allura virtualenv
exec { "create allura venv":
  command => "/usr/local/bin/virtualenv env-allura",
  cwd     => "/home/vagrant",
  creates => "/home/vagrant/env-allura",
  user => "vagrant",
  group => "vagrant",
  require => Exec[ "install venv" ],
}

# create dir for Allura source
file { "/home/vagrant/src":
  ensure => "directory",
  owner => "vagrant",
  group => "vagrant",
}

# create dir for Allura logs
file { "/var/log/allura":
  ensure => "directory",
  owner => "vagrant",
  group => "vagrant",
}

# clone Allura source from git
exec { "clone repo":
  command => "/usr/bin/git clone https://git-wip-us.apache.org/repos/asf/incubator-allura.git allura",
  cwd     => "/vagrant",
  creates => "/vagrant/allura",
  user => "vagrant",
  group => "vagrant",
  require => [ Package[ "git-core" ] ],
}

# symlink allura src into the vagrant home dir just to be nice
file { '/home/vagrant/src/allura':
  ensure => 'link',
  target => '/vagrant/allura',
  require => [ File['/home/vagrant/src'], Exec['clone repo'] ],
}

# install Allura dependencies
exec { "pip install":
  command => "/home/vagrant/env-allura/bin/pip install -r requirements.txt",
  cwd     => "/vagrant/allura",
  # user => "vagrant",
  # group => "vagrant",
  timeout => 0,
  logoutput => true,
  returns => 0,
  tries => 3,
  require => [ Exec[ "clone repo"], Exec[ "create allura venv" ],
               File["/usr/lib/libjpeg.so"], File["/usr/lib/libz.so"],
               ],
}

# symlink pysvn in from the system installation
file { '/home/vagrant/env-allura/lib/python2.7/site-packages/pysvn':
  ensure => 'link',
  target => '/usr/lib/python2.7/dist-packages/pysvn',
  require => [ Package[ "python-svn" ], Exec[ "pip install" ]],
}

# create SCM repo dirs
file { [ "/home/vagrant/scm", "/home/vagrant/scm/git", "/home/vagrant/scm/hg", "/home/vagrant/scm/svn" ]:
  ensure => "directory",
  owner => "vagrant",
  group => "vagrant",
  mode   => 777,
}

# create symlinks to repo dirs
file { '/git':
  ensure => "link",
  target => "/home/vagrant/scm/git",
  owner => "vagrant",
  group => "vagrant",
}

file { '/hg':
  ensure => "link",
  target => "/home/vagrant/scm/hg",
  owner => "vagrant",
  group => "vagrant",
}

file { '/svn':
  ensure => "link",
  target => "/home/vagrant/scm/svn",
  owner => "vagrant",
  group => "vagrant",
}
