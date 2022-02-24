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
from ming.orm import ThreadLocalORMSession, session
from tg import tmpl_context as c
from allura import model as M
from forgediscussion.model import ForumPost
from allura.lib import utils, security
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, ArgumentTypeError


log = logging.getLogger(__name__)


def arguments():
    parser = ArgumentParser(description="Args for changing anon comment permissions",
                            formatter_class=ArgumentDefaultsHelpFormatter, )
    parser.add_argument('shortname', help="shortname of project to change perms on")
    parser.add_argument('toolname', help="toolname to change perms on")

    args = parser.parse_args()
    return args


def main():
    args = arguments()

    c.project = None # to avoid error in Artifact.__mongometa__.before_save
    project = M.Project.query.get(shortname=args.shortname)
    tool = project.app_config_by_tool_type(args.toolname)

    for chunk in utils.chunked_find(ForumPost, {'app_config_id':tool._id}):
        for p in chunk:
            has_access = bool(security.has_access(p, 'moderate', M.User.anonymous()))

            if has_access:
                anon_role_id = None
                for acl in p.acl:
                    # find the anon moderate acl
                    if acl.permission == 'moderate' and acl.access=='ALLOW':
                        anon_role_id = acl.role_id

                if anon_role_id:
                    print(f"revoking anon moderate privelege for '{p._id}'")
                    security.simple_revoke(p.acl, anon_role_id, 'moderate')
                    session(p).flush(p)


if __name__ == '__main__':
    main()
