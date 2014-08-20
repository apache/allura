import unittest
from mock import patch

from allura import model as M


class TestThread(unittest.TestCase):

    @patch('allura.model.artifact.c')
    def test_should_update_index(self, c):
        p = M.Thread()
        self.assertFalse(p.should_update_index({}, {}))
        old = {'num_views': 1}
        new = {'num_views': 2}
        self.assertFalse(p.should_update_index(old, new))
        old = {'num_views': 1, 'a': 1}
        new = {'num_views': 2, 'a': 1}
        self.assertFalse(p.should_update_index(old, new))
        old = {'num_views': 1, 'a': 1}
        new = {'num_views': 2, 'a': 2}
        self.assertTrue(p.should_update_index(old, new))
