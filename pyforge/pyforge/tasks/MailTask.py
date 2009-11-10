# -*- coding: utf-8 -*-
from celery.task import Task
from celery.registry import tasks

class MailTask(Task):
    routing_key = 'forge.mail'

    def run(self, **kwargs)
        logger = self.get_logger(**kwargs)
        logger.debug("Fetched mail message")

tasks.register(MailTask)
