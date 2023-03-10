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
BASE_PATH = (toplevel_dir,) #freeze main path

def run(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdout, so that pytest can capture it
    (stdout, stderr) = proc.communicate()
    sys.stdout.write(stdout.decode('utf-8'))
    sys.stderr.write(stderr.decode('utf-8'))
    return proc.returncode


find_py = r"find Allura Forge* -not -path '*/\.*' -name '*.py'"


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
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + r"' | xargs grep -v '^ *#' | egrep -n '\bprint\(' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")


def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1, 123]:
        raise Exception('These should not use tab chars')


def test_ruff():
    cmd = f"ruff check . --config {BASE_PATH[0]}/ruff.toml --show-source"
    if run(cmd) != 0:
        # print 'Command was: %s' % cmd
        raise Exception('ruff failure, see stdout')

