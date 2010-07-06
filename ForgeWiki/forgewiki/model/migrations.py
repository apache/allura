import cPickle as pickle
from itertools import chain

import pymongo
from ming.orm import state
from pylons import c

from flyway import Migration
from pyforge.model import Thread, AppConfig, ArtifactReference
from forgewiki.model import Page

class WikiMigration(Migration):

    def __init__(self, *args, **kwargs):
        super(WikiMigration, self).__init__(*args, **kwargs)
        try:
            c.project
        except TypeError:
            class EmptyClass(): pass
            c._push_object(EmptyClass())
            c.project = EmptyClass()
            c.project._id = None
            c.app = EmptyClass()
            c.app.config = EmptyClass()
            c.app.config.options = EmptyClass()
            c.app.config.options.mount_point = None


class V0(WikiMigration):
    '''Migrate Thread.artifact_id to Thread.artifact_reference'''
    version = 0

    def up(self):
        for pg in self.ormsession.find(Page):
            q1 = self.ormsession.find(Thread, dict(artifact_id=pg._id))
            q2 = self.ormsession.find(Thread, {'artifact_reference.artifact_id':pg._id})
            for t in chain(q1, q2):
                t.artifact_reference = self._dump_ref(pg)
                t.artifact_id = None
                self.ormsession.update_now(t, state(t))
        self.ormsession.flush()

    def down(self):
        for pg in self.ormsession.find(Page):
            for t in self.ormsession.find(Thread, dict(artifact_reference=self._dump_ref(pg))):
                t.artifact_id = pg._id
                t.artifact_reference = None
                self.ormsession.update_now(t, state(t))
        self.ormsession.flush()


    def _dump_ref(self, art):
        app_config = self.ormsession.get(AppConfig, art.app_config_id)
        return ArtifactReference(dict(
            project_id=app_config.project_id,
            mount_point=app_config.options.mount_point,
            artifact_type=pymongo.bson.Binary(pickle.dumps(art.__class__)),
            artifact_id=art._id))


class AddDeletedAttribute(WikiMigration):
    version = 1

    def up(self):
        for pg in self.ormsession.find(Page):
            pg.deleted = False
        self.ormsession.flush()

    def down(self):
        for pg in self.ormsession.find(Page):
            del pg.deleted
        self.ormsession.flush()
