# This file contains python variables that configure Lamson for email processing.
import logging

relay_config = {'host': 'localhost', 'port': 8825}

receiver_config = {'host': 'localhost', 'port': 8823}

handlers = ['app.handlers.sample', 'app.handlers.index', 'app.handlers.amqp', 'app.handlers.react']

router_defaults = {'host': 'localhost'}

template_config = {'dir': 'app', 'module': 'templates'}

# this is for when you run the config.queue boot
queue_config = {'queue': 'run/posts', 'sleep': 10}

queue_handlers = ['app.handlers.index']

# the config/boot.py will turn these values into variables set in settings
