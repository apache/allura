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

from tg import tmpl_context as c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils

log = logging.getLogger('update-ordinals')
log.addHandler(logging.StreamHandler(sys.stdout))


def main():
    test = sys.argv[-1] == 'test'
    num_projects_examined = 0
    log.info('Examining all projects for mount order.')
    for some_projects in utils.chunked_find(M.Project):
        for project in some_projects:
            c.project = project
            mounts = project.ordered_mounts(include_hidden=True)

            # ordered_mounts() means duplicate ordinals (if any) will be next
            # to each other
            duplicates_found = False
            prev_ordinal = None
            for mount in mounts:
                if mount['ordinal'] == prev_ordinal:
                    duplicates_found = True
                    break
                prev_ordinal = mount['ordinal']

            if duplicates_found:
                if test:
                    log.info('Would renumber mounts for project "%s".' %
                             project.shortname)
                else:
                    log.info('Renumbering mounts for project "%s".' %
                             project.shortname)
                    for i, mount in enumerate(mounts):
                        if 'ac' in mount:
                            mount['ac'].options['ordinal'] = i
                        elif 'sub' in mount:
                            mount['sub'].ordinal = i
                    ThreadLocalORMSession.flush_all()

            num_projects_examined += 1
            session(project).clear()

        log.info('%s projects examined.' % num_projects_examined)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
