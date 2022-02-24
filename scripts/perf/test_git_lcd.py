#!/usr/bin/env python

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

import sys
import os
from glob import glob
from time import time
from contextlib import contextmanager
from pprint import pprint

from mock import Mock
from forgegit.model.git_repo import GitImplementation


@contextmanager
def benchmark():
    timer = {'start': time()}
    yield timer
    timer['end'] = time()
    timer['result'] = timer['end'] - timer['start']


def main(repo_dir, sub_dir='', commit=None):
    repo_dir = repo_dir.rstrip('/')
    git = GitImplementation(Mock(full_fs_path=repo_dir))
    commit = Mock(_id=commit or git.head)
    paths = glob(os.path.join(repo_dir, sub_dir, '*'))
    paths = [path.replace(repo_dir + '/', '', 1) for path in paths]
    print(f"Timing LCDs for {paths} at {commit._id}")
    with benchmark() as timer:
        result = git.last_commit_ids(commit, paths)
    pprint(result)
    print("Took %f seconds" % timer['result'])

if __name__ == '__main__':
    main(*sys.argv[1:])
