#!/bin/bash

# Create log dir
if [ ! -d /var/log/allura ]
then
    sudo mkdir -p /var/log/allura
    sudo chown vagrant:vagrant /var/log/allura
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
    echo -e "\n# Activate Allura virtualenv\n. /home/vagrant/anvil/bin/activate && cd /home/vagrant/src/forge" >> /home/vagrant/.bash_profile
    chown vagrant:vagrant /home/vagrant/.bash_profile
fi

. /home/vagrant/anvil/bin/activate

cd /home/vagrant/src/forge

# Setup Allura python packages
echo "Setting up Allura python packages..."
for APP in Allura* Forge* NoWarnings
do
    pushd $APP
    python setup.py develop
    popd
done

echo "Purging unneeded packages..."
aptitude clean
aptitude -y -q purge ri
aptitude -y -q purge installation-report landscape-common wireless-tools wpasupplicant ubuntu-serverguide
aptitude -y -q purge python-dbus libnl1 python-smartpm linux-headers-2.6.32-21-generic python-twisted-core libiw30
aptitude -y -q purge python-twisted-bin libdbus-glib-1-2 python-pexpect python-pycurl python-serial python-gobject python-pam libffi5

echo "Zeroing free space to aid VM compression..."
cat /dev/zero > zero.fill;sync;sleep 1;sync;rm -f zero.fill
dd if=/dev/zero of=/EMPTY bs=1M
rm -f /EMPTY
