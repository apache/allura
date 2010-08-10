import os
import shutil
import unittest
import pkg_resources

from pylons import c, g

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge.lib import helpers as h
from forgesvn import model as SM

class TestSVNApp(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_templates(self):
        assert c.app.templates.endswith('forgesvn/templates')

    def test_admin_menu(self):
        assert len(c.app.admin_menu()) == 1
        assert c.app.admin_menu()[0].label == 'Viewable Files'

    def test_uninstall(self):
        c.app.uninstall(c.project)
        assert g.mock_amq.pop('audit')
        g.mock_amq.setup_handlers()
        c.app.uninstall(c.project)
        g.mock_amq.handle_all()

