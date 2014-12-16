FROM ubuntu:12.04

RUN apt-get update && apt-get install -y \
    default-jre-headless \
    git-core \
    python-dev \
    python-pip \
    libjpeg8-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    zlib1g-dev
# TODO: make SVN support an option
RUN apt-get install -y \
    subversion \
    python-svn
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10 && \
    echo 'deb http://downloads-distro.mongodb.org/repo/ubuntu-upstart dist 10gen' > /etc/apt/sources.list.d/mongodb.list && \
    apt-get update && \
    apt-get install -y mongodb-org

RUN pip install virtualenv

# TODO better base dir instead of /root/
ENV basedir /root
WORKDIR ${basedir}
RUN virtualenv env-allura
RUN . env-allura/bin/activate

# TODO use `ADD .` instead?
RUN mkdir src && \
    cd src && \
    git clone https://git-wip-us.apache.org/repos/asf/allura.git allura
RUN cd src/allura && \
    pip install -r requirements.txt
# TODO: make SVN support an option
RUN ln -s /usr/lib/python2.7/dist-packages/pysvn ~/env-allura/lib/python2.7/site-packages/

RUN cd src/allura && \
    ./rebuild-all.bash

# TODO better solr installation
RUN cd src && \
    wget -nv http://archive.apache.org/dist/lucene/solr/4.2.1/solr-4.2.1.tgz && \
    tar xf solr-4.2.1.tgz && rm -f solr-4.2.1.tgz && \
    cp -f allura/solr_config/schema.xml solr-4.2.1/example/solr/collection1/conf && \
RUN cd src/solr-4.2.1/example/ && \
    mkdir ${basedir}/logs/ && \
    nohup java -jar start.jar > ${basedir}/logs/solr.log &

RUN mkdir /srv/git && mkdir /srv/svn && mkdir /srv/hg && \
    #chown $USER /srv/git && chmod /srv/svn && chmod /srv/hg && \
    chmod 775 /srv/git && chmod 755 /srv/svn && chmod 755 /srv/hg

RUN service mongod start && sleep 16

#WORKDIR src/allura/Allura
#RUN nohup paster taskd development.ini > ${basedir}/logs/taskd.log &
#RUN paster setup-app development.ini

#RUN nohup paster serve --reload development.ini > ${basedir}/logs/tg.log &

