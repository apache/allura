import unittest

from pylons import c, g

from ming.orm import ThreadLocalORMSession

from allura.tests import helpers
from allura.lib import helpers as h

from forgehg.reactors import reactors as R

class TestHgReactors(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src-hg')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        R.init('scm.hg.init', {})

