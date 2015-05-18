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

import argparse
import logging

from ming.odm import session
from pylons import tmpl_context as c

from allura.scripts import ScriptTask
from allura.model import Post
from allura.lib.utils import chunked_find
from forgediscussion.model import ForumPost


log = logging.getLogger(__name__)


class CreateDeletedComments(ScriptTask):

    @classmethod
    def execute(cls, options):
        models = [Post, ForumPost]
        # Find all posts that have parent_id, but does not have actual parent
        # and create fake parent for them
        for model in models:
            for chunk in chunked_find(model, {'parent_id': {'$ne': None}}):
                for post in chunk:
                    if not post.parent:
                        log.info('Creating deleted parent for %s %s',
                                 model.__mongometa__.name, post._id)
                        c.project = post.app_config.project
                        slug = post.slug.rsplit('/', 1)[0]
                        full_slug = post.full_slug.rsplit('/', 1)[0]
                        author = c.project.admins()[0]
                        deleted_post = model(
                            _id=post.parent_id,
                            deleted=True,
                            text="Automatically created in place of deleted post",
                            app_id=post.app_id,
                            app_config_id=post.app_config_id,
                            discussion_id=post.discussion_id,
                            thread_id=post.thread_id,
                            author_id=author._id,
                            slug=slug,
                            full_slug=full_slug,
                        )
                        session(deleted_post).flush(deleted_post)

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(
            description='Create comments marked as deleted in place of '
                        'actually deleted parent comments (ticket:#1731)'
        )
        return parser


if __name__ == '__main__':
    CreateDeletedComments.main()
