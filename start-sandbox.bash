#!/bin/bash

# Start RabbitMQ
sudo rabbitmq-server &
rabbitmqctl add_user test test
rabbitmqctl add_vhost test
rabbitmqctl set_permissions -p test test "" ".*" ".*"


# Start SOLR, as per SOG-sandbox location
pushd /usr/local/solr
java -jar start.jar &
popd


# Start mongo, already on the path
mongod &


# Start the forge
. sandbox-env/bin/activate
cd pyforge
paster reactor_setup sandbox.ini
paster reactor sandbox.ini &

paster setup-app sandbox.ini
paster serve sandbox.ini &

