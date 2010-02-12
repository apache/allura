sudo su -
mkdir ~/Build
cd ~/Build
wget http://www.python.org/ftp/python/2.6.4/Python-2.6.4.tgz
tar -zxvf Python-2.6.4.tgz
./configure --prefix=/opt/python
make;make install
mkdir -p /data/db
# setup 'gitosis' user for ssh
# use setup-sandbox.bash
# git clone ssh://engr.geek.net/forge /opt/forge
# use setup-common.bash, with changes as follows:
#   ci box:
#     virtualenv --no-site-packages ci-env
#   demo box:
#     virtualenv --no-site-packages demo-env
#   both:
#     git clone git://github.com/rick446/mongo-python-driver.git /opt/pymongo
#     git clone git://merciless.git.sourceforge.net/gitroot/merciless/merciless /opt/Ming
# all references to "python setup.py develop" change to "python26 setup.py develop
# sudo yum install rabbitmq-server
# sudo yum install java
# instead of using "sandbox.ini", use either "ci.ini" or "demo.ini" depending on webhead
