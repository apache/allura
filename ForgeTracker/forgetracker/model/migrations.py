import cPickle as pickle
from itertools import chain

import pymongo
from ming.orm import state
from pylons import c

from flyway import Migration
from allura.model import Thread, AppConfig, ArtifactReference
from forgetracker.model import Ticket, Globals


class TrackerMigration(Migration):
    def __init__(self, *args, **kwargs):
        super(TrackerMigration, self).__init__(*args, **kwargs)
        try:
            c.project
        except (TypeError, AttributeError), exc:
            class EmptyClass(): pass
            c._push_object(EmptyClass())
            c.project = EmptyClass()
            c.project._id = None
            c.app = EmptyClass()
            c.app.config = EmptyClass()
            c.app.config.options = EmptyClass()
            c.app.config.options.mount_point = None


class V0(TrackerMigration):
    '''Migrate Thread.artifact_id to Thread.artifact_reference'''
    version = 0

    def up(self):
        for pg in self.ormsession.find(Ticket):
            q1 = self.ormsession.find(Thread, dict(artifact_id=pg._id))
            q2 = self.ormsession.find(Thread, {'artifact_reference.artifact_id':pg._id})
            for t in chain(q1, q2):
                t.artifact_reference = self._dump_ref(pg)
                t.artifact_id = None
                self.ormsession.update_now(t, state(t))
        self.ormsession.flush()

    def down(self):
        for pg in self.ormsession.find(Ticket):
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


class AddShowInSearchAttributeToAllCustomFields(TrackerMigration):
    version = 1

    def up(self):
        for custom_field in self.each_custom_field():
            custom_field['show_in_search'] = False
        self.ormsession.flush()

    def down(self):
        for custom_field in self.each_custom_field():
            del custom_field['show_in_search']
        self.ormsession.flush()

    def each_custom_field(self):
        for tracker_globals in self.ormsession.find(Globals):
            for custom_field in tracker_globals.custom_fields:
                yield custom_field

