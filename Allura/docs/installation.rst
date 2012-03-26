Installation
=================

Easy Setup
---------------

Our easy setup instructions are in our README.rst file.  You can read it online at https://sourceforge.net/p/allura/git/#readme

You should be able to get Allura up and running in well under an hour by following those instructions.

Enabling inbound email
----------------------

Allura can listen for email messages and update tools and artifacts.  For example, every ticket has an email address, and
emails sent to that address will be added as comments on the ticket.  To set up the SMTP listener, run::

(anvil)~/src/forge/Allura$ nohup paster smtp_server development.ini > ~/logs/smtp.log &

By default this uses port 8825.  Depending on your mail routing, you may need to change that port number.
And if the port is in use, this command will fail.  You can check the log file for any errors.
To change the port number, edit `development.ini` and change `forgemail.port` to the appropriate port number for your environment.


Enabling RabbitMQ
-----------------

For faster notification of background jobs, you can use RabbitMQ.  Assuming a base setup from the README, run these commands
to install rabbitmq and set it up::

(anvil)~$ sudo aptitude install rabbitmq-server
(anvil)~$ sudo rabbitmqctl add_user testuser testpw
(anvil)~$ sudo rabbitmqctl add_vhost testvhost
(anvil)~$ sudo rabbitmqctl set_permissions -p testvhost testuser ""  ".*" ".*"
(anvil)~$ pip install amqplib==0.6.1 kombu==1.0.4

Then edit Allura/development.ini and change `amqp.enabled = false` to `amqp.enabled = true` and uncomment the other `amqp` settings.

If your `paster taskd` process is still running, restart it::

(anvil)~/src/forge/Allura$ pkill -f taskd
(anvil)~/src/forge/Allura$ nohup paster taskd development.ini > ~/logs/taskd.log &
