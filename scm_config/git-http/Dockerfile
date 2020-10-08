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


# loosely inspired by https://github.com/jacksoncage/apache-docker/blob/ubuntu/Dockerfile
# not inspired by https://hub.docker.com/_/httpd/ which does a custom source-based install of httpd

# match main allura Dockerfile, for shared base
FROM ubuntu:18.04

# libapache2-mod-python is for py2 (both ubuntu:18.04 and ubuntu:20.04)
# to match that, python-requests is also py2 on ubuntu:18.04 (probably python2-requests on ubuntu:20.04)
# https://forge-allura.apache.org/p/allura/tickets/8352/ is to switch to mod_wsgi & py3 instead
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-python \
    python-requests \
    git \
    curl \
    sudo \
    && rm -rf /var/lib/apt/lists/*


ENV APACHE_RUN_USER www-data
ENV APACHE_RUN_GROUP www-data
ENV APACHE_LOG_DIR /var/log/apache2
ENV APACHE_PID_FILE /var/run/apache2.pid
ENV APACHE_RUN_DIR /var/run/apache2
ENV APACHE_LOCK_DIR /var/lock/apache2
ENV APACHE_SERVERADMIN admin@localhost
ENV APACHE_SERVERNAME localhost
ENV APACHE_SERVERALIAS docker.localhost
ENV APACHE_DOCUMENTROOT /var/www

RUN a2enmod cgi proxy proxy_http

ADD ./git-http.conf /etc/apache2/sites-available/
RUN a2dissite 000-default.conf
RUN a2ensite git-http.conf
RUN apachectl configtest

ADD git-http-backend-wrapper.sh /usr/lib/git-core
RUN adduser www-data sudo
RUN echo '%sudo  ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/sudo_group_passwordless

CMD ["/usr/sbin/apache2", "-D", "FOREGROUND"]