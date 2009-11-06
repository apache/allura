from datetime import datetime
from sf.gobble.lib import sf_updater
from sf.gobble.queueworkers import QueueWorker

class RelationsWorker(QueueWorker):
    routing_keys=['sf-relations.#']

    def handle(self, shortname, source, **kwargs):
        return sf_updater.update_relations_data(shortname, source, self.host, **kwargs)


class AdaptiveWorker(QueueWorker):

    def handle(self, shortname, source, **kwargs):
        was_changed, project = self.adaptive_handle(shortname, source, **kwargs)
        # Schedule next update
        now = datetime.utcnow()
        if project:
            project.updated = now
            if was_changed:
                project.last_changed = now
            next_time = project.next_update(self.update_type, was_changed)
            self.current_task.reschedule(next_time)
            self.log.debug('Rescheduled task %s for project %s:%s (changed=%s) to %s',
                           self.current_task._id, source, shortname, was_changed, next_time)
        return True

    def adaptive_handle(self, shortname, source, **kwargs):
        '''should return (was_changed, project) where

        was_changed - the message actually performed an update
        project - the Gutenberg project object referenced by shortname/source
        '''
        raise NotImplementedError, 'adaptive_handle'


class TestWorker(QueueWorker):
    routing_keys=['test']

    def handle(self, shortname, source, **kwargs):
        self.log.info('%s@%s' % (shortname, source))
        self.log.info(kwargs)
        assert False
        return True
