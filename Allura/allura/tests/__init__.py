# -*- coding: utf-8 -*-
"""Unit and functional test suite for allura."""

import alluratest.controller


class TestController(alluratest.controller.TestController):
    """
    Base functional test case for the controllers.

    """

    application_under_test = 'main_without_authn'
