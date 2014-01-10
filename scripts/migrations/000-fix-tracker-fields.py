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
import logging

from pylons import tmpl_context as c

from ming.orm import session

from allura import model as M
from forgetracker import model as TM

log = logging.getLogger(__name__)


def main():
    test = sys.argv[-1] == 'test'
    projects = M.Project.query.find().all()
    log.info('Fixing tracker fields')
    for p in projects:
        if p.parent_id:
            continue
        c.project = p
        q = TM.Globals.query.find()
        if not q.count():
            continue
        for g in q:
            if g.open_status_names:
                continue
            if g.status_names is None:
                old_names = ['open', 'closed']
            else:
                old_names = g.status_names.split() or ['open', 'closed']
            if g.open_status_names is None:
                g.open_status_names = ' '.join(
                    name for name in old_names if name != 'closed')
            if g.closed_status_names is None:
                g.closed_status_names = 'closed'
        if test:
            log.info('... would fix tracker(s) in %s', p.shortname)
        else:
            log.info('... fixing tracker(s) in %s', p.shortname)
            session(g).flush()
        session(g).clear()

if __name__ == '__main__':
    main()
