#!/bin/bash
./setup-sandbox.bash

# Start RabbitMQ
# sudo rabbitmq-server & # already started for us
rabbitmqctl add_user testuser testpw
rabbitmqctl add_vhost testvhost
rabbitmqctl set_permissions -p testvhost testuser "" ".*" ".*"


# Start SOLR, as per SOG-sandbox location
pushd /usr/local/solr
java -jar start.jar &
popd


# Start mongo, already on the path
# mongod & # already started for us


# Start the forge
. sandbox-env/bin/activate
cd pyforge
paster reactor_setup sandbox.ini
paster reactor sandbox.ini &

paster setup-app sandbox.ini
paster serve sandbox.ini &

