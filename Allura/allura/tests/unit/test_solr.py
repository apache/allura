import unittest
import mock

from allura.lib.solr import Solr

class TestSolr(unittest.TestCase):
    @mock.patch('allura.lib.solr.pysolr')
    def setUp(self, pysolr):
        self.solr = Solr('server', commit=False, commitWithin='10000')

    @mock.patch('allura.lib.solr.pysolr')
    def test_add(self, pysolr):
        s = self.solr
        s.add('foo', commit=True, commitWithin=None)
        pysolr.Solr.add.assert_called_once_with(s, 'foo', commit=True,
                commitWithin=None)
        pysolr.reset_mock()
        s.add('bar', somekw='value')
        pysolr.Solr.add.assert_called_once_with(s, 'bar', commit=False,
                commitWithin='10000', somekw='value')

    @mock.patch('allura.lib.solr.pysolr')
    def test_delete(self, pysolr):
        s = self.solr
        s.delete('foo', commit=True)
        pysolr.Solr.delete.assert_called_once_with(s, 'foo', commit=True)
        pysolr.reset_mock()
        s.delete('bar', somekw='value')
        pysolr.Solr.delete.assert_called_once_with(s, 'bar', commit=False,
                somekw='value')
