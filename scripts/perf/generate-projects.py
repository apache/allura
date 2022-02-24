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

import re
from ming.odm import ThreadLocalORMSession
from allura import model as M

def main(start, cnt):
    n = M.Neighborhood.query.get(url_prefix='/p/')
    admin = M.User.by_username('admin1')
    #M.Project.query.remove({'shortname': re.compile('gen-proj-.*')})
    #ThreadLocalORMSession.flush_all()
    for i in range(start, cnt):
        name = f'gen-proj-{i}'
        project = n.register_project(name, admin)
        if (i-start) > 0 and (i-start) % 100 == 0:
            print(f'Created {i-start} projects')
    print('Flushing...')
    ThreadLocalORMSession.flush_all()
    print('Done')

if __name__ == '__main__':
    import sys
    start = int(sys.argv[1])
    cnt = int(sys.argv[2])
    main(start, cnt)
