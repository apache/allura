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
from functools import wraps
import contextlib

from ming.orm.ormsession import ThreadLocalORMSession
from pylons import tmpl_context as c
from mock import patch
import tg
from paste.deploy.converters import asbool

from allura import model as M


def with_user_project(username):
    def _with_user_project(func):
        @wraps(func)
        def wrapped(*args, **kw):
            user = M.User.by_username(username)
            c.user = user
            n = M.Neighborhood.query.get(name='Users')
            shortname = 'u/' + username
            p = M.Project.query.get(shortname=shortname, neighborhood_id=n._id)
            if not p:
                n.register_project(shortname, user=user, user_project=True)
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()
            return func(*args, **kw)
        return wrapped
    return _with_user_project


@contextlib.contextmanager
def NullContextManager():
    yield


def with_tool(project_shortname, ep_name, mount_point=None, mount_label=None,
        ordinal=None, post_install_hook=None, username='test-admin',
        **override_options):
    def _with_tool(func):
        @wraps(func)
        def wrapped(*args, **kw):
            c.user = M.User.by_username(username)
            p = M.Project.query.get(shortname=project_shortname)
            c.project = p
            if mount_point and not p.app_instance(mount_point):
                c.app = p.install_app(ep_name, mount_point, mount_label, ordinal, **override_options)
                if post_install_hook:
                    post_install_hook(c.app)

                if asbool(tg.config.get('smtp.mock')):
                    smtp_mock = patch('allura.lib.mail_util.smtplib.SMTP')
                else:
                    smtp_mock = NullContextManager()
                with smtp_mock:
                    while M.MonQTask.run_ready('setup'):
                        pass
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()
            elif mount_point:
                c.app = p.app_instance(mount_point)
            return func(*args, **kw)
        return wrapped
    return _with_tool

with_discussion = with_tool('test', 'Discussion', 'discussion')
with_link = with_tool('test', 'Link', 'link')
with_tracker = with_tool('test', 'Tickets', 'bugs')
with_wiki = with_tool('test', 'Wiki', 'wiki')
with_url = with_tool('test', 'ShortUrl', 'url')

class raises(object):
    'test helper in the form of a context manager, to assert that something raises an exception'

    def __init__(self, ExcType):
        self.ExcType = ExcType

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_t):
        if exc_type:
            if issubclass(exc_type, self.ExcType):
                # ok
                return True
            else:
                # root exception will be raised, untouched
                return False
        else:
            raise AssertionError('Did not raise %s' % self.ExcType)


def without_module(*module_names):
    def _without_module(func):
        @wraps(func)
        def wrapped(*a, **kw):
            with patch.dict(sys.modules, {m: None for m in module_names}):
                return func(*a, **kw)
        return wrapped
    return _without_module
