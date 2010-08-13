import unittest

from pylons import c, g

from ming.orm import ThreadLocalORMSession

from allura.tests import helpers
from allura.lib import helpers as h

class TestGitApp(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src-git')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_templates(self):
        assert c.app.templates.endswith('forgegit/templates')

    def test_admin_menu(self):
        assert len(c.app.admin_menu()) == 1

    def test_uninstall(self):
        c.app.uninstall(c.project)
        assert g.mock_amq.pop('audit')
        g.mock_amq.setup_handlers()
        c.app.uninstall(c.project)
        g.mock_amq.handle_all()
