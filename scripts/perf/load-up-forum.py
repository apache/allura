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


import logging
import uuid
from ming.orm import ThreadLocalORMSession, session
from tg import tmpl_context as c
from allura import model as M
from forgediscussion.model import ForumPost, Forum
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, ArgumentTypeError
from allura.lib import helpers as h
from random import randint


log = logging.getLogger(__name__)


def arguments():
    parser = ArgumentParser(description="Args for changing anon comment permissions",
                            formatter_class=ArgumentDefaultsHelpFormatter, )
    parser.add_argument('shortname', help="shortname of project to change ")
    parser.add_argument('mountpt', help="toolname ")
    parser.add_argument('forumname', help="forum")

    args = parser.parse_args()
    return args


def main():
    args = arguments()

    c.user = M.User.query.get(username='root')

    with h.push_context(args.shortname, args.mountpt, neighborhood='Projects'):

        tool = c.project.app_config_by_tool_type(args.mountpt)

        # create tons of topics
        discussion = Forum.query.get(
            app_config_id=tool._id,
            shortname=args.forumname)

        for i in range(5000):
            subject = f'fake topic {str(i)}'
            thd = discussion.thread_class()(discussion_id=discussion._id, subject=subject)
            # subj = str(uuid.uuid4())[:8]
            p = thd.post(subject, 'a new topic 2')

            for j in range(randint(1, 5)):
                new_post = {'text':'comment text'}
                # post = thd.add_post(**new_post)
                post = thd.add_post(text='comment text for real', subject="test subject")

            if i % 1000:
                session(p).flush()


if __name__ == '__main__':
    main()
