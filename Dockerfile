#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

FROM ubuntu:18.04

RUN apt-get update && apt-get install -y \
    git-core \
    python2.7-dev \
    libssl-dev \
    libldap2-dev \
    libsasl2-dev \
    libjpeg8-dev \
    zlib1g-dev \
    python-pip \
    zip \
    subversion \
    python-svn \
    curl \
    locales \
    sudo

# up-to-date version of node & npm
RUN curl --silent --location https://deb.nodesource.com/setup_10.x | sudo bash - && \
    apt-get install --yes nodejs

# Snapshot generation for SVN (and maybe other SCMs) might fail without this
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

# GitPython uses this to determine current user when committing (used in
# tests). If this is not set, it uses os.getlogin, which fails inside docker.
ENV USER root

WORKDIR /allura
ENV PYTHONUNBUFFERED 1
CMD gunicorn --paste Allura/docker-dev.ini --reload
