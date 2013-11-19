..     Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.

Installation
=================

Installation
---------------

Our step-by-step setup instructions are in our INSTALL.markdown file.  You can read it online at https://forge-allura.apache.org/p/allura/git/ci/master/tree/INSTALL.markdown  You should be able to get Allura up and running in well under an hour by following those instructions.

For a faster and easier setup, see our `Vagrant/VirtualBox installation guide <https://forge-allura.apache.org/p/allura/wiki/Install%20and%20Run%20Allura%20-%20Vagrant/>`_

Enabling inbound email
----------------------

Allura can listen for email messages and update tools and artifacts.  For example, every ticket has an email address, and
emails sent to that address will be added as comments on the ticket.  To set up the SMTP listener, run::

(env-allura)~/src/forge/Allura$ nohup paster smtp_server development.ini > ~/logs/smtp.log &

By default this uses port 8825.  Depending on your mail routing, you may need to change that port number.
And if the port is in use, this command will fail.  You can check the log file for any errors.
To change the port number, edit `development.ini` and change `forgemail.port` to the appropriate port number for your environment.


Enabling RabbitMQ
-----------------

For faster notification of background jobs, you can use RabbitMQ.  Assuming a base setup from the INSTALL, run these commands
to install rabbitmq and set it up::

(env-allura)~$ sudo aptitude install rabbitmq-server
(env-allura)~$ sudo rabbitmqctl add_user testuser testpw
(env-allura)~$ sudo rabbitmqctl add_vhost testvhost
(env-allura)~$ sudo rabbitmqctl set_permissions -p testvhost testuser ""  ".*" ".*"
(env-allura)~$ pip install amqplib==0.6.1 kombu==1.0.4

Then edit Allura/development.ini and change `amqp.enabled = false` to `amqp.enabled = true` and uncomment the other `amqp` settings.

If your `paster taskd` process is still running, restart it::

(env-allura)~/src/forge/Allura$ pkill -f taskd
(env-allura)~/src/forge/Allura$ nohup paster taskd development.ini > ~/logs/taskd.log &
