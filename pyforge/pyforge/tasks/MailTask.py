# -*- coding: utf-8 -*-
from celery.task import Task
from celery.registry import tasks

class MailTask(Task):
    routing_key = 'forge.mail'

    def run(self, *args, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.info("Fetched mail message")
        logger.info('Args = %s', repr(args))
        logger.info('KwArgs = %s', repr(kwargs))

tasks.register(MailTask)
print 'Imported tasks.MailTask'
