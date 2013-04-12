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
 "mongodb-server",
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
  command => "/usr/local/bin/virtualenv --system-site-packages anvil",
  cwd     => "/home/vagrant",
  creates => "/home/vagrant/anvil",
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
  command => "/usr/bin/git clone git://git.code.sf.net/p/allura/git.git forge",
  cwd     => "/home/vagrant/src",
  creates => "/home/vagrant/src/forge",
  user => "vagrant",
  group => "vagrant",
  require => [ File[ "/home/vagrant/src" ], Package[ "git-core" ] ],
}

# install Allura dependencies
exec { "/home/vagrant/anvil/bin/pip install -r requirements.txt":
  cwd     => "/home/vagrant/src/forge",
  user => "vagrant",
  group => "vagrant",
  timeout => 0,
  require => [ Exec[ "clone repo"], Exec[ "create allura venv" ] ],
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
