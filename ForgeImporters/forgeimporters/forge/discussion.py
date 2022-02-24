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

import json
from dateutil.parser import parse

from tg import tmpl_context as c
from tg import app_globals as g
from ming.orm import session, ThreadLocalORMSession

from tg import (
    expose,
    flash,
    redirect
)

from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash
)

from forgeimporters.base import (
    ToolImportForm,
    ToolImportController,
    File,
    save_importer_upload
)

from allura import model as M
from allura.lib.decorators import require_post
from allura.lib import validators as v
from allura.lib import helpers as h

from forgediscussion import utils

from forgeimporters.forge.alluraImporter import AlluraImporter


class ForgeDiscussionImportForm(ToolImportForm):
    discussions_json = v.JsonFile(not_empty=True)


class ForgeDiscussionImportController(ToolImportController):
    import_form = ForgeDiscussionImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.forge:templates/discussion/index.html')
    def index(self, **kw):
        return dict(importer=self.importer, target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, discussions_json, mount_point, mount_label, **kw):
        if self.importer.enforce_limit(c.project):
            save_importer_upload(
                            c.project,
                            'discussions.json',
                            json.dumps(discussions_json)
                        )
            self.importer.post(mount_point=mount_point, mount_label=mount_label)
            flash('Discussion import has begun. Your new discussion will be available when the import is complete')
        else:
            flash('There are too many imports pending at this time. Please wait and try again.', 'error')
        redirect(c.project.url() + 'admin/')


class ForgeDiscussionImporter(AlluraImporter):

    source = 'Allura'
    target_app_ep_names = 'discussion'
    controller = ForgeDiscussionImportController
    tool_label = 'Discussion'
    tool_description = 'Import an allura discussion.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _load_json(self, project):
        return self._load_json_by_filename(project, 'discussions.json')

    def import_tool(self, project, user, mount_point=None, mount_label=None, **kw):
        discussion_json = self._load_json(project)

        mount_point = mount_point or 'discussion'
        mount_label = mount_label or 'Discussion'

        app = project.install_app('discussion', mount_point, mount_label, import_id={'source': self.source})
        ThreadLocalORMSession.flush_all()

        with h.push_config(c, app=app):

            # Deleting the forums that are created by default
            self._clear_forums(app)

            try:
                M.session.artifact_orm_session._get().skip_mod_date = True

                for forum_json in discussion_json['forums']:

                    new_forum = dict(
                                    app_config_id=app.config._id,
                                    shortname=forum_json['shortname'],
                                    description=forum_json['description'],
                                    name=forum_json['name'],
                                    create='on',
                                    parent='',
                                    members_only=False,
                                    anon_posts=False,
                                    monitoring_email=None,
                    )

                    forum = utils.create_forum(app, new_forum=new_forum)

                    if "import_id" in list(forum_json.keys()):
                        forum.import_id = forum_json["import_id"]

                    for thread_json in forum_json["threads"]:
                        thread = forum.get_discussion_thread(dict(headers=dict(Subject=thread_json['subject'])))[0]

                        if "import_id" in thread_json:
                            thread.import_id = thread_json["import_id"]

                        self.add_posts(thread, thread_json['posts'], app)

                    session(forum).flush(forum)
                    session(forum).expunge(forum)

                M.AuditLog.log(
                    "import tool {} from exported Allura JSON".format(
                        app.config.options.mount_point,
                    ),
                    project=project,
                    user=user,
                    url=app.url,
                )

                g.post_event('project_updated')
                ThreadLocalORMSession.flush_all()
                return app
            except Exception:
                h.make_app_admin_only(app)
                raise
            finally:
                M.session.artifact_orm_session._get().skip_mod_date = False

    def _clear_forums(self, app):
        forums = app.forums
        for forum in forums:
            forum.delete()

    def annotate_text(self, text, user, username):
        label = " created"

        return self.annotate(text, user, username, label)

    def add_posts(self, thread, posts, app):
        created_posts = []

        for post_json in posts:
            username = post_json["author"]
            user = self.get_user(username)

            with h.push_config(c, user=user, app=app):
                timestamp = parse(post_json['timestamp'])

                # For nested posts
                parent_id = None
                slug = ''
                if "slug" in list(post_json.keys()):
                    slug = post_json["slug"]

                    if slug.count('/') >= 1:
                        pos = slug.rindex('/')
                        parent_slug = slug[:pos]

                        for cp in created_posts:
                            if cp.get(parent_slug, None) is not None:
                                parent_id = cp[parent_slug]._id
                                break

                p = thread.add_post(
                        subject=post_json['subject'],
                        text=self.annotate_text(post_json['text'], user, username),
                        timestamp=timestamp,
                        ignore_security=True,
                        parent_id=parent_id
                )

                if ("last_edited" in post_json) and (post_json["last_edited"] is not None):
                    p.last_edit_date = parse(post_json["last_edited"])

                p.add_multiple_attachments(
                        [File(a["url"]) for a in post_json["attachments"]]
                    )

                if slug != '':
                    created_posts.append({slug: p})
