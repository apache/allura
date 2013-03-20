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
  command => "/usr/local/bin/virtualenv anvil",
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
  command => "/usr/bin/git clone https://git-wip-us.apache.org/repos/asf/incubator-allura.git allura",
  cwd     => "/home/vagrant/src",
  creates => "/home/vagrant/src/allura",
  user => "vagrant",
  group => "vagrant",
  require => [ File[ "/home/vagrant/src" ], Package[ "git-core" ] ],
}

# install Allura dependencies
exec { "pip install":
  command => "/home/vagrant/anvil/bin/pip install -r requirements.txt",
  cwd     => "/home/vagrant/src/allura",
  user => "vagrant",
  group => "vagrant",
  timeout => 0,
  logoutput => true,
  returns => 0,
  tries => 3,
  require => [ Exec[ "clone repo"], Exec[ "create allura venv" ],
               File["/usr/lib/libjpeg.so"], File["/usr/lib/libz.so"],
               ],
}

# symlink pysvn in from the system installation
file { '/home/vagrant/anvil/lib/python2.7/site-packages/pysvn':
  ensure => 'link',
  target => '/usr/lib/python2.7/dist-packages/pysvn',
  require => [ Package[ "python-svn" ], Exec[ "pip install" ]],
}
# and trick pip/setuptools etc to know its there
file { '/home/vagrant/anvil/lib/python2.7/site-packages/pysvn-1.7.5-py2.7.egg-info':
  ensure => 'directory',
  require => File['/home/vagrant/anvil/lib/python2.7/site-packages/pysvn'],
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
