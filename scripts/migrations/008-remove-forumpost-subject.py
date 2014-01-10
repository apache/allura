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

"""
Remove the subject FieldProperty from all ForumPost objects. [#2071]
"""

import logging
import sys

from allura import model as M

log = logging.getLogger(__name__)

c_forumpost = M.project_doc_session.db.forum_post


def main():
    test = sys.argv[-1] == 'test'

    forum_posts = c_forumpost.find()
    for fp in forum_posts:
        try:
            s = fp['subject']
            if test:
                log.info('... would remove subject "%s" from %s', s, fp['_id'])
            else:
                log.info('... removing subject "%s" from %s', s, fp['_id'])
                del fp['subject']
                c_forumpost.save(fp)
        except KeyError:
            log.info('... no subject property on %s', fp['_id'])

if __name__ == '__main__':
    main()
