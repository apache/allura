#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.
import functools
import unittest

from decorator import decorator

testcase = unittest.TestCase(methodName='__init__')  # py2 needs a methodName that is a valid attr :/


def with_setup(setup, teardown=None):
    # this might have subtle ordering differences from a true "setup" method, esp. if other decorators are involved
    def with_setup__wrapper(func):
        @functools.wraps(func)
        def with_setup__decorated(*a, **kw):
            try:
                setup()
                return func(*a, **kw)
            finally:
                if teardown:
                    teardown()
        return with_setup__decorated
    return with_setup__wrapper


def raises(ExcType):
    @decorator
    def inner_raises(func, *a, **kw):
        with testcase.assertRaises(ExcType):
            return func(*a, **kw)
    return inner_raises


def assert_equal(*a, **kw):
    return testcase.assertEqual(*a, **kw)


def assert_equals(*a, **kw):
    return testcase.assertEqual(*a, **kw)


def assert_not_equal(*a, **kw):
    return testcase.assertNotEqual(*a, **kw)


def assert_raises(*a, **kw):
    return testcase.assertRaises(*a, **kw)


def assert_is_none(*a, **kw):
    return testcase.assertIsNone(*a, **kw)


def assert_is_not_none(*a, **kw):
    return testcase.assertIsNotNone(*a, **kw)


def assert_is(*a, **kw):
    return testcase.assertIs(*a, **kw)


def assert_true(*a, **kw):
    return testcase.assertTrue(*a, **kw)


def assert_false(*a, **kw):
    return testcase.assertFalse(*a, **kw)


def assert_in(*a, **kw):
    return testcase.assertIn(*a, **kw)


def assert_not_in(*a, **kw):
    return testcase.assertNotIn(*a, **kw)


def assert_less(*a, **kw):
    return testcase.assertLess(*a, **kw)


def assert_greater(*a, **kw):
    return testcase.assertGreater(*a, **kw)


def assert_greater_equal(*a, **kw):
    return testcase.assertGreaterEqual(*a, **kw)


def assert_regexp_matches(*a, **kw):
    return testcase.assertRegex(*a, **kw)


#
# copied from IPython.testing.decorators
#   BSD license
def module_not_available(module):
    """Can module be imported?  Returns true if module does NOT import.

    This is used to make a decorator to skip tests that require module to be
    available, but delay the 'import numpy' to test execution time.
    """
    try:
        mod = __import__(module)
        mod_not_avail = False
    except ImportError:
        mod_not_avail = True

    return mod_not_avail
