from sf.gobble.lib import fm_updater
from sf.gobble.queueworkers import QueueWorker

class FMProjectWorker(QueueWorker):
    routing_keys=['fm.#']
    # Hints for run-worker.py
    source = 'freshmeat.net'
    update_type = 'project'

    def parse(self, message):
        return message['project'], 'freshmeat.net', {}

    def handle(self, shortname, source, **kwargs):
        return fm_updater.update_project(shortname, source, self.host, **kwargs)
