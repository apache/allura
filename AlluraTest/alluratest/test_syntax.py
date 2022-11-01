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

import os.path
from subprocess import Popen, PIPE
import sys

from unittest import SkipTest
from six.moves import zip_longest

toplevel_dir = os.path.abspath(os.path.dirname(__file__) + "/../..")


def run(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdout, so that pytest can capture it
    (stdout, stderr) = proc.communicate()
    sys.stdout.write(stdout.decode('utf-8'))
    sys.stderr.write(stderr.decode('utf-8'))
    return proc.returncode


find_py = r"find Allura Forge* -not -path '*/\.*' -name '*.py'"


# a recipe from itertools doc
def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fillvalue, *args)


def test_no_local_tz_functions():
    if run(find_py + r" | xargs grep '\.now(' ") not in [1, 123]:
        raise Exception("These should use .utcnow()")
    if run(find_py + r" | xargs grep '\.fromtimestamp(' ") not in [1, 123]:
        raise Exception("These should use .utcfromtimestamp()")
    if run(find_py + " | xargs grep 'mktime(' ") not in [1, 123]:
        raise Exception("These should use calendar.timegm()")


def test_no_prints():
    skips = [
        '/tests/',
        'Allura/allura/command/',
        'Allura/ldap-setup.py',
        'Allura/ldap-userconfig.py',
        '/scripts/',
        'ForgeSVN/setup.py',
    ]
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + "' | xargs grep -v '^ *#' | grep 'print ' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")


def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1, 123]:
        raise Exception('These should not use tab chars')


def run_linter(files):
    raise SkipTest('pylint see [#8346]')
    if run('pylint -E --disable=all --enable=exposed-api-needs-kwargs --load-plugins alluratest.pylint_checkers {}'.format(' '.join(files))) != 0:
        raise Exception('Custom Allura pylint errors found.')


def run_pyflakes(files):
    # skip some that aren't critical errors
    skips = [
        'imported but unused',
        'redefinition of unused',
        'assigned to but never used',
        '__version__',
    ]
    files = [f for f in files if '/migrations/' not in f]
    cmd = "pyflakes " + ' '.join(files) + " | grep -v '" + "' | grep -v '".join(skips) + "'"
    if run(cmd) != 1:
        # print 'Command was: %s' % cmd
        raise Exception('pyflakes failure, see stdout')


class TestLinters:
    # this will get populated dynamically with test methods, see below
    pass


# Dynamically generate many test methods, to run pylint & pyflakes commands in separate batches
# Can't use http://nose.readthedocs.io/en/latest/writing_tests.html#test-generators because nose doesn't run
# those in parallel
def create_many_lint_methods():
    proc = Popen(find_py, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    (find_stdout, stderr) = proc.communicate()
    find_stdout = find_stdout.decode('utf-8')
    stderr = stderr.decode('utf-8')
    sys.stderr.write(stderr)
    assert proc.returncode == 0, proc.returncode
    py_files = find_stdout.split('\n')

    for i, files in enumerate(grouper(40, py_files)):
        files = [_f for _f in files if _f]
        if not files:
            continue

        lint_test_method = lambda self, these_files=files: run_linter(these_files)
        lint_test_method.__name__ = str(f'test_pylint_{i}')
        setattr(TestLinters, f'test_pylint_{i}', lint_test_method)

        pyflake_test_method = lambda self, these_files=files: run_pyflakes(these_files)
        pyflake_test_method.__name__ = str(f'test_pyflakes_{i}')
        setattr(TestLinters, f'test_pyflakes_{i}', pyflake_test_method)


create_many_lint_methods()
