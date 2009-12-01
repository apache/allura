# -*- coding: utf-8 -*-
from celery.registry import tasks
import pysolr

from .base import Task

class AddArtifacts(Task):
    routing_key = 'forge.solr'

    def run(self, server, *artifacts, **kwargs):
        logger = self.get_logger(**kwargs)
        for a in artifacts:
            logger.info("Adding artifact: %s", a['id'])
        solr =  pysolr.Solr(server)
        try:
            solr.add(list(artifacts))
            solr.commit()
        except Exception, ex:
            logger.info('Exception: %s (%r)', ex, ex.args)
            raise
        logger.info("Added artifacts")

class DelArtifacts(Task):
    routing_key = 'forge.solr'

    def run(self, server, *artifact_ids, **kwargs):
        logger = self.get_logger(**kwargs)
        solr =  pysolr.Solr(server)
        for aid in artifact_ids:
            logger.info("Deleting artifact: %s", aid)
            solr.delete(id=aid)
        solr.commit()
        logger.info("Deleted artifacts")

class TestTask(Task):
    routing_key = 'forge.solr'

    def run(self, *args, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.info("Deleted artifacts")
        logger.info("Ran test with %s, %s", repr(args), repr(kwargs))


tasks.register(AddArtifacts)
tasks.register(DelArtifacts)
tasks.register(TestTask)
