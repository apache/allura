from pylons import c

from flyway import Migration
from pyforge.model import Thread
from forgetracker.model import Ticket

class V0(Migration):
    '''Migrate Thread.artifact_id to Thread.artifact_reference'''
    version = 0

    def __init__(self, *args, **kwargs):
        super(V0, self).__init__(*args, **kwargs)
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

    def up(self):
        for pg in self.ormsession.find(Ticket):
            for t in self.ormsession.find(Thread, dict(artifact_id=pg._id)):
                t.artifact_reference = pg.dump_ref()
                t.artifact_id = None
        self.ormsession.flush()

    def down(self):
        for pg in self.ormsession.find(Ticket):
            for t in self.ormsession.find(Thread, dict(artifact_reference=pg.dump_ref())):
                t.artifact_id = pg._id
                t.artifact_reference = None
        self.ormsession.flush()


