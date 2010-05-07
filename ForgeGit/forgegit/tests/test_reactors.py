import unittest

from pylons import c, g

from ming.orm import ThreadLocalORMSession

from pyforge.tests import helpers
from pyforge.lib import helpers as h

from forgegit.reactors import reactors as R

class TestGitReactors(unittest.TestCase):

    def setUp(self):
        helpers.setup_basic_test()
        helpers.setup_global_objects()
        h.set_context('test', 'src_git')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_init(self):
        R.init('scm.git.init', {})

    def test_refresh_commit(self):
        h1='6e29319896bf86d52e3d73bd203524e65804a273'
        h2='b505490e129a1b47bef98b9f52afb8bc10fff938'
        R.refresh_commit('scm.git.init', {'hash':'%s..%s' % (h1,h2)})
