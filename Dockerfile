FROM ubuntu:12.04

RUN apt-get update && apt-get install -y \
    git-core \
    python-dev \
    libssl-dev \
    libldap2-dev \
    libsasl2-dev \
    libjpeg8-dev \
    zlib1g-dev \
    python-pip

ENV basedir /allura

ADD . ${basedir}
WORKDIR ${basedir}

RUN pip install -r requirements.txt
RUN ./rebuild-all.bash
