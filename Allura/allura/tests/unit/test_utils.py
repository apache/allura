import unittest

from alluratest.controller import setup_unit_test
from allura.lib.utils import generate_code_stats

class TestCodeStats(unittest.TestCase):

    def setUp(self):
        setup_unit_test()

    def test_generate_code_stats(self):
        code = \
"""class Person(object):
    
    def __init__(self, name='Alice'):
        self.name = name

    def greetings(self):
        print "Hello, %s" % self.name
\t\t"""

        stats = generate_code_stats(code)
        assert stats['line_count'] == 8
        assert stats['data_line_count'] == 5
        assert stats['code_size'] == len(code)
