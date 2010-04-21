from pylons import c
from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.websetup import bootstrap
from pyforge.lib import helpers as h
from forgetracker.tests import run_app_setup


def setUp():
    run_app_setup()


class TestWithModel(object):
    def setUp(self):
        bootstrap.wipe_database()
        c.user = bootstrap.create_user('Test User')
        neighborhood = bootstrap.create_neighborhood('Projects', c.user)
        c.project = neighborhood.register_project('test', c.user)
        app = c.project.install_app('Tickets', 'bugs')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'bugs')

    def tearDown(self):
        ThreadLocalORMSession.close_all()

