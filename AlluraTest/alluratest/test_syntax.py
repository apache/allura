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

toplevel_dir = os.path.abspath(os.path.dirname(__file__) + "/../..")


def run(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that nosetests can capture it
    (stdout, stderr) = proc.communicate()
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return proc.returncode

find_py = "find Allura Forge* -name '*.py'"

# a recepe from itertools doc
from itertools import izip_longest


def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)


def test_pyflakes():
    # skip some that aren't critical errors
    skips = [
        'imported but unused',
        'redefinition of unused',
        'assigned to but never used',
        '__version__',
    ]
    proc = Popen(find_py, shell=True, cwd=toplevel_dir,
                 stdout=PIPE, stderr=PIPE)
    (find_stdout, stderr) = proc.communicate()
    sys.stderr.write(stderr)
    assert proc.returncode == 0, proc.returncode

    # run pyflakes in batches, so it doesn't take tons of memory
    error = False
    all_files = [f for f in find_stdout.split('\n')
                 if '/migrations/' not in f and f.strip()]
    for files in grouper(20, all_files, fillvalue=''):
        cmd = "pyflakes " + \
            ' '.join(files) + " | grep -v '" + \
            "' | grep -v '".join(skips) + "'"
        # print 'Command was: %s' % cmd
        retval = run(cmd)
        if retval != 1:
            print
            # print 'Command was: %s' % cmd
            print 'Returned %s' % retval
            error = True

    if error:
        raise Exception('pyflakes failure, see stdout')


def test_no_local_tz_functions():
    if run(find_py + " | xargs grep '\.now(' ") not in [1, 123]:
        raise Exception("These should use .utcnow()")
    if run(find_py + " | xargs grep '\.fromtimestamp(' ") not in [1, 123]:
        raise Exception("These should use .utcfromtimestamp()")
    if run(find_py + " | xargs grep 'mktime(' ") not in [1, 123]:
        raise Exception("These should use calendar.timegm()")


def test_no_prints():
    skips = [
        '/tests/',
        'Allura/allura/command/',
        'Allura/ldap-setup.py',
        'Allura/ldap-userconfig.py',
        'Allura/ez_setup/',
        'Allura/allura/lib/AsciiDammit.py',
        '/scripts/',
        'ForgeSVN/setup.py',
    ]
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + "' | xargs grep -v '^ *#' | grep 'print ' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")


def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1, 123]:
        raise Exception('These should not use tab chars')

def test_linters():
    if run(find_py + ' | xargs pylint -E --disable=all --enable=exposed-api-needs-kwargs --load-plugins alluratest.pylint_checkers') != 0:
        raise Exception('Custom Allura pylint errors found.')
