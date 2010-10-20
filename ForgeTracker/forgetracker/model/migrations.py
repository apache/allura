import cPickle as pickle
from itertools import chain

import pymongo
from ming.orm import state
from pylons import c

from flyway import Migration
from allura.model import Thread, AppConfig, ArtifactReference, ProjectRole
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


class AddSaveSearchesPermission(TrackerMigration):
    version = 2

    def up(self):
        first_ticket = self.ormsession.find(Ticket).first()
        if first_ticket:
            app_config = self.ormsession.get(AppConfig, first_ticket.app_config_id)
            app_config.acl.save_searches = []
            developer = self.ormsession.find(ProjectRole, dict(name='Developer')).first()
            admin = self.ormsession.find(ProjectRole, dict(name='Admin')).first()
            if developer:
                app_config.acl.save_searches.append(developer._id)
            if admin:
                app_config.acl.save_searches.append(admin._id)
            self.ormsession.flush()

    def down(self):
        first_ticket = self.ormsession.find(Ticket).first()
        if first_ticket:
            app_config = self.ormsession.get(AppConfig, first_ticket.app_config_id)
            del app_config.acl.save_searches
            self.ormsession.flush()


class SplitStatusNamesIntoOpenAndClosed(TrackerMigration):
    version = 3

    def up(self):
        for tracker_globals in self.ormsession.find(Globals):
            old_names = tracker_globals.status_names
            tracker_globals.open_status_names = ' '.join([name for name in old_names.split(' ') if name and name != 'closed'])
            tracker_globals.closed_status_names = 'closed'
            tracker_globals.status_names = ''
        self.ormsession.flush()
        self.ormsession.clear()

    def down(self):
        for tracker_globals in self.ormsession.find(Globals):
            tracker_globals.status_names = ' '.join([tracker_globals.open_status_names, tracker_globals.closed_status_names])
            tracker_globals.open_status_names = ''
            tracker_globals.closed_status_names = ''
        self.ormsession.flush()
        self.ormsession.clear()

class MoveMilestonesToCustom(TrackerMigration):
    version = 4

    def _custom_field(self, tracker_globals):
        names = tracker_globals.milestone_names or ''
        return dict(
            name='_milestone',
            show_in_search=True,
            type='milestone',
            label='Milestone',
            milestones=[
                dict(name=name, complete=False, due_date=None)
                for name in names.split() ])

    def up(self):
        for tracker_globals in self.ormsession.find(Globals):
            fld = self._custom_field(tracker_globals)
            tracker_globals.custom_fields.append(fld)
        self.ormsession.flush()
        self.ormsession.clear()

    def down(self):
        for tracker_globals in self.ormsession.find(Globals):
            fld = self._custom_field(tracker_globals)
            if tracker_globals.custom_fields[-1] == fld:
                tracker_globals.custom_fields.pop()
        self.ormsession.flush()
        self.ormsession.clear()

class FixMilestonesAndTickets(TrackerMigration):
    version = 5

    def up(self):
        for tracker_globals in self.ormsession.find(Globals):
            for fld in tracker_globals.custom_fields:
                if 'name' not in fld:
                    fld.name = '_' + fld.label.lower()
                if 'show_in_search' not in fld:
                    fld.show_in_search = True
        for ticket in self.ormsession.find(Ticket):
            ticket.custom_fields['_milestone'] = ticket.milestone
        self.ormsession.flush()
        self.ormsession.clear()

    
