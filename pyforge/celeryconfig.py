# -*- coding: utf-8 -*-
CELERY_BACKEND = "mongodb"
CARROT_BACKEND = "amqp"

# We shouldn't need to supply these because we're using Mongo,
# but Celery gives us errors if we don't.
DATABASE_ENGINE = "sqlite3"
DATABASE_NAME = "celery.db"

AMQP_SERVER = "localhost"
AMQP_PORT = 5672
AMQP_VHOST = "celeryvhost"
AMQP_USER = "celeryuser"
AMQP_PASSWORD = "celerypw"

CELERYD_LOG_FILE = "celeryd.log"
CELERYD_PID_FILE = "celeryd.pid"
CELERYD_DAEMON_LOG_LEVEL = "INFO"

CELERY_MONGODB_BACKEND_SETTINGS = {
    "host":"localhost",
    "port":27017,
    "database":"celery"
}

CELERY_AMQP_EXCHANGE = "tasks"
CELERY_AMQP_PUBLISHER_ROUTING_KEY = "task.regular"
CELERY_AMQP_EXCHANGE_TYPE = "topic"
CELERY_AMQP_CONSUMER_QUEUE = "forge_tasks"
CELERY_AMQP_CONSUMER_ROUTING_KEY = "forge.#"

CELERY_IMPORTS = ("pyforge.tasks.MailTask")
