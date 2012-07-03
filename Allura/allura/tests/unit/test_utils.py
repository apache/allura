import unittest
from mock import Mock

from alluratest.controller import setup_unit_test
from allura.lib.utils import generate_code_stats, chunked_list

class TestCodeStats(unittest.TestCase):

    def setUp(self):
        setup_unit_test()

    def test_generate_code_stats(self):
        blob = Mock()
        blob.text = \
"""class Person(object):

    def __init__(self, name='Alice'):
        self.name = name

    def greetings(self):
        print "Hello, %s" % self.name
\t\t"""
        blob.size = len(blob.text)

        stats = generate_code_stats(blob)
        assert stats['line_count'] == 8
        assert stats['data_line_count'] == 5
        assert stats['code_size'] == len(blob.text)


class TestUtils(unittest.TestCase):
    def test_chunked_list(self):
        l = range(10)
        chunks = list(chunked_list(l, 3))
        self.assertEqual(len(chunks), 4)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual([el for sublist in chunks for el in sublist], l)
