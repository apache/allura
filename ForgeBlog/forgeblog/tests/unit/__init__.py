from pylons import c
from ming.orm.ormsession import ThreadLocalORMSession

from allura.websetup import bootstrap
from allura.lib import helpers as h
from allura.lib import plugin
from allura import model as M
from alluratest.controller import setup_basic_test


def setUp():
    setup_basic_test()

class BlogTestWithModel(object):
    def setUp(self):
        bootstrap.wipe_database()
        project_reg = plugin.ProjectRegistrationProvider.get()
        c.user = bootstrap.create_user('Test User')
        neighborhood = M.Neighborhood(name='Projects', url_prefix='/p/',
            features=dict(private_projects = False,
                          max_projects = None,
                          css = 'none',
                          google_analytics = False))
        project_reg.register_neighborhood_project(neighborhood, [c.user])
        c.project = neighborhood.register_project('test', c.user)
        c.project.install_app('Blog', 'blog')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'blog', neighborhood='Projects')

    def tearDown(self):
        ThreadLocalORMSession.close_all()
