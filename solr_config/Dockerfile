FROM ubuntu:12.04

RUN apt-get update && apt-get install -y \
    default-jre-headless \
    wget \
    tar

ENV basedir /solr

ADD . ${basedir}
WORKDIR ${basedir}

RUN wget -nv http://archive.apache.org/dist/lucene/solr/4.2.1/solr-4.2.1.tgz
RUN tar xf solr-4.2.1.tgz && rm -f solr-4.2.1.tgz
RUN cp -f schema.xml solr-4.2.1/example/solr/collection1/conf
