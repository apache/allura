#!/bin/bash

# Start SOLR, as per SOG-sandbox location
pushd /usr/local/solr
java -jar start.jar &
popd

# Start mongo, already on the path
mongod &

. sandbox-env/bin/activate
cd pyforge
paster setup-app sandbox.ini
paster serve sandbox.ini &

