#!/bin/bash
./setup-sandbox.bash

# Start RabbitMQ
# sudo rabbitmq-server & # already started for us
rabbitmqctl add_user testuser testpw
rabbitmqctl add_vhost testvhost
rabbitmqctl add_vhost vhost_testing
rabbitmqctl set_permissions -p testvhost testuser "" ".*" ".*"
rabbitmqctl set_permissions -p vhost_testing testuser "" ".*" ".*"


# Start SOLR, as per SOG-sandbox location
SOLRCONFIG="$(pwd)/solr_config"
pushd /usr/local/solr
/usr/java/jdk1.5.0_15/bin/java -Dsolr.solr.home="$SOLRCONFIG" -jar start.jar &
popd


# Start mongo, already on the path
# mongod & # already started for us
# Start a second instance of mongo for tests
mkdir -p /data/db-test
mongod --port 27018 --dbpath /data/db-test &


# Start the forge
. sandbox-env/bin/activate
cd pyforge
paster reactor_setup sandbox.ini
paster reactor sandbox.ini &
paster smtp_server sandbox.ini &

paster reactor_setup sandbox-test.ini#main_with_amqp

paster setup-app sandbox.ini
paster serve --reload --daemon sandbox.ini

sleep 5
echo "########################################"
echo "The forge is running."
echo "########################################"
