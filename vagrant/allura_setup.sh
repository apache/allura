#!/bin/bash

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

# Install mongodb
MONGODB_VERSION=2.2.3
MONGODB_PKG_URL="deb http://downloads-distro.mongodb.org/repo/ubuntu-upstart dist 10gen"
MONGODB_SRC_LST=/etc/apt/sources.list.d/10gen.list
if [ "$(mongo --version 2>/dev/null | sed 's/.*: //')" != "$MONGODB_VERSION" ]
then
  echo "Installing Mongodb $MONGODB_VERSION..."
  sudo apt-get -y -q purge mongodb mongodb-clients mongodb-server mongodb-dev
  sudo apt-get -y -q purge mongodb-10gen
  sudo apt-get -y -q autoremove
  rm -rf /var/lib/mongodb/* 2>/dev/null
  apt-key adv --keyserver keyserver.ubuntu.com --recv 7F0CEB10
  grep -q "$MONGODB_PKG_URL" $MONGODB_SRC_LST || echo "$MONGODB_PKG_URL" >> $MONGODB_SRC_LST
  apt-get -y -q update
  apt-get -y -q install mongodb-10gen=$MONGODB_VERSION
  echo "mongodb-10gen hold" | dpkg --set-selections
fi

# Install Solr
cd /home/vagrant/src
if [ ! -d solr-4.2.1 ]
then
    echo "Installing Solr..."
    wget -nv http://archive.apache.org/dist/lucene/solr/4.2.1/solr-4.2.1.tgz
    tar xf solr-4.2.1.tgz && rm -f solr-4.2.1.tgz
    cp -f allura/solr_config/schema.xml solr-4.2.1/example/solr/collection1/conf
    chown -R vagrant:vagrant /home/vagrant/src/solr-4.2.1
fi

# Create startup script
if [ ! -f /home/vagrant/start_allura ]
then
    echo "Creating ~/start_allura script..."
    cp /vagrant/start_allura /home/vagrant
    chown vagrant:vagrant /home/vagrant/start_allura
fi

# Create .bash_profile with venv activation
if [ ! -f /home/vagrant/.bash_profile ]
then
    echo "Creating ~/.bash_profile ..."
    cp /home/vagrant/.profile /home/vagrant/.bash_profile
    echo -e "\n# Activate Allura virtualenv\n. /home/vagrant/env-allura/bin/activate && cd /home/vagrant/src/allura" >> /home/vagrant/.bash_profile
    chown vagrant:vagrant /home/vagrant/.bash_profile
fi

# Make sure vagrant user has full ownership of venv
sudo chown -R vagrant:vagrant /home/vagrant/env-allura/

# Setup Allura python packages
cd /home/vagrant/src/allura
sudo -u vagrant bash -c '. /home/vagrant/env-allura/bin/activate; ./rebuild-all.bash'

echo "Purging unneeded packages..."
aptitude clean
aptitude -y -q purge ri
aptitude -y -q purge installation-report landscape-client landscape-common wireless-tools wpasupplicant
aptitude -y -q purge python-dbus libnl1 python-smartpm linux-headers-server python-twisted-core libiw30 language-selector-common
aptitude -y -q purge cloud-init juju python-twisted python-twisted-bin libdbus-glib-1-2 python-pexpect python-serial python-gobject python-pam accountsservice libaccountsservice0

echo "Done with allura_setup.sh"

# sometimes mongo ends up stopped
# maybe due to that disk-filling exercise
# make sure it's still running
service mongodb status
if [ "$?" -ne "0" ]; then
	rm /var/lib/mongodb/mongod.lock
	service mongodb start
fi
