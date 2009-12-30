#!/bin/bash
./setup-common.bash

echo
echo '# downloading and untarring solr'
mkdir download install
pushd download
wget http://apache.mirrors.tds.net/lucene/solr/1.4.0/apache-solr-1.4.0.tgz
cd ../install
tar xzf ../download/apache-solr-1.4.0.tgz
popd
