from pylons import c
from ming.orm.ormsession import ThreadLocalORMSession

from allura.websetup import bootstrap
from allura.lib import helpers as h
from allura import model as M
from allura.tests.helpers import run_app_setup


def setUp():
    run_app_setup()


class TrackerTestWithModel(object):
    def setUp(self):
        bootstrap.wipe_database()
        c.user = bootstrap.create_user('Test User')
        neighborhood = M.Neighborhood(name='Projects',
                                 url_prefix='/p/',
                                 acl=dict(read=[None], create=[],
                                          moderate=[c.user._id], admin=[c.user._id]))
        c.project = neighborhood.register_project('test', c.user)
        app = c.project.install_app('Tickets', 'bugs')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'bugs')

    def tearDown(self):
        ThreadLocalORMSession.close_all()

