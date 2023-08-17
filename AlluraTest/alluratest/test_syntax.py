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
import re
from subprocess import Popen, PIPE
import sys

dir = os.path.abspath(os.path.dirname(__file__) + "/..")


def run(cmd, dir=dir):
    proc = Popen(cmd, shell=True, cwd=dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that test suite can capture it
    (stdout, stderr) = proc.communicate()
    stdout = stdout.decode('utf-8')
    stderr = stderr.decode('utf-8')
    if re.match(r'xargs: .* No such file', stderr):
        raise Exception(stderr)
    print(stdout, end='')
    print(stderr, end='', file=sys.stderr)
    return (proc.returncode, proc.communicate())


def test_run_precommit():
    cmd = "pre-commit run --all-files"
    code, outputs = run(cmd, dir=os.environ.get('ALLURA_GIT_DIR'))
    if code != 0:
        raise Exception(f'pre-commit failed to run: {outputs[0].decode()} {outputs[1].decode()}')

