from config import settings
from lamson.routing import Router
from lamson.server import Relay, QueueReceiver
from lamson import view
import logging
import logging.config
import jinja2

logging.config.fileConfig("config/logging.conf")

# the relay host to actually send the final message to
settings.relay = Relay(host=settings.relay_config['host'], 
                       port=settings.relay_config['port'], debug=1)

# where to listen for incoming messages
settings.receiver = QueueReceiver(settings.queue_config['queue'],
                                  settings.queue_config['sleep'])

settings.database = configure_database(settings.database_config, also_create=False)

Router.defaults(**settings.router_defaults)
# NOTE: this is using a different handlers variable in settings
Router.load(settings.queue_handlers)
Router.RELOAD=True

view.LOADER = jinja2.Environment(
    loader=jinja2.PackageLoader(settings.template_config['dir'], 
                                settings.template_config['module']))

