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
import argparse
import logging

from ming.odm import session
from pylons import tmpl_context as c

from allura.scripts import ScriptTask
from allura import model as M
from allura.lib.utils import chunked_find
from forgediscussion.model import ForumPost


log = logging.getLogger(__name__)


class CreateDeletedComments(ScriptTask):

    @classmethod
    def execute(cls, options):
        models = [M.Post, ForumPost]
        app_config_id = cls.get_tool_id(options.tool)
        # Find all posts that have parent_id, but does not have actual parent
        # and create fake parent for them
        for model in models:
            q = {'parent_id': {'$ne': None},
                 'app_config_id': app_config_id}
            for chunk in chunked_find(model, q):
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
                        if options.dry_run:
                            session(deleted_post).expunge(deleted_post)
                        else:
                            session(deleted_post).flush(deleted_post)

    @classmethod
    def get_tool_id(cls, tool):
        _n, _p, _mount = tool.split('/')
        n = M.Neighborhood.query.get(url_prefix='/{}/'.format(_n))
        if not n:
            log.error('Can not find neighborhood %s', _n)
            sys.exit(1)
        p = M.Project.query.get(neighborhood_id=n._id, shortname=_p)
        if not p:
            log.error('Can not find project %s', _p)
            sys.exit(1)
        t = p.app_instance(_mount)
        if not t:
            log.error('Can not find tool with mount point %s', _mount)
            sys.exit(1)
        return t.config._id

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(
            description='Create comments marked as deleted in place of '
                        'actually deleted parent comments (ticket:#1731)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Show comments that will be created, but do not actually '
                 'create anything',
        )
        parser.add_argument(
            '-t', '--tool',
            required=True,
            help='Create comments only in specified tool, e.g. p/test/wiki')
        return parser


if __name__ == '__main__':
    CreateDeletedComments.main()
