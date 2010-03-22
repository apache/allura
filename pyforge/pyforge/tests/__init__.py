# -*- coding: utf-8 -*-
"""Unit and functional test suite for pyforge."""

from . import helpers

__all__ = ['setup_db', 'teardown_db', 'TestController', 'helpers']

def setup_db():
    """Method used to build a database"""
    pass

def teardown_db():
    """Method used to destroy a database"""
    pass


class TestController(object):
    def setUp(self):
        """Method called by nose before running each test"""
        self.app = helpers.setup_functional_test()
    
    def tearDown(self):
        """Method called by nose after running each test"""
        pass
