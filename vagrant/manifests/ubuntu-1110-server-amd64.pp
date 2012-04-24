# create puppet group
group { "puppet": 
  ensure => "present", 
}

# install required system packages
Package { ensure => "installed" }

$packages = [
 "git-core",
 "subversion",
 "python-svn",
 "libtidy-0.99-0",
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

package { $packages: }

file { '/usr/lib/libz.so':
  ensure => 'link',
  target => '/usr/lib/x86_64-linux-gnu/libz.so',
  require => Package[ "zlib1g-dev" ],
}

# install python pip
exec { "install venv":
  command => "/usr/bin/pip install virtualenv",
  creates => "/usr/local/bin/virtualenv",
  require => Package[ "python-pip" ],
}

# create Allura virtualenv
exec { "create allura venv":
  command => "/usr/local/bin/virtualenv --system-site-packages anvil && chown -R vagrant:vagrant /home/vagrant/anvil",
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

# pre-install Paste and PasteDeploy to work around problem in TG2 install
exec { "prereqs":
  command => "/home/vagrant/anvil/bin/pip install Paste==1.7.5.1 PasteDeploy==1.5.0",
  user => "vagrant",
  group => "vagrant",
  require => Exec[ "create allura venv" ],
}

# install remainder of Allura dependencies
exec { "/usr/bin/sudo /home/vagrant/anvil/bin/pip install -r requirements.txt":
  cwd     => "/home/vagrant/src/forge",
  user => "vagrant",
  group => "vagrant",
  timeout => 0,
  require => [ Exec[ "clone repo"], Exec[ "prereqs" ] ],
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


