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
import sys
import re
from functools import wraps
import contextlib
from six.moves.urllib.parse import parse_qs

from ming.orm.ormsession import ThreadLocalORMSession
from tg import tmpl_context as c
from mock import patch
import tg
from paste.deploy.converters import asbool

from allura import model as M
import allura.config.middleware


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
                c.app = p.install_app(
                    ep_name, mount_point, mount_label, ordinal, **override_options)
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


class raises:

    '''
    Test helper in the form of a context manager, to assert that something raises an exception.
    After completion, the 'exc' attribute can be used to do further inspection of the exception
    '''

    def __init__(self, ExcType):
        self.ExcType = ExcType
        self.exc = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_t):
        if exc_type:
            self.exc = exc_val
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


class patch_middleware_config:

    '''
    Context manager that patches the configuration used during middleware
    setup for Allura
    '''

    def __init__(self, new_configs):
        self.new_configs = new_configs

    def __enter__(self):
        self._make_app = allura.config.middleware.make_app

        def make_app(global_conf, full_stack=True, **app_conf):
            app_conf.update(self.new_configs)
            return self._make_app(global_conf, full_stack, **app_conf)

        allura.config.middleware.make_app = make_app

        return self

    def __exit__(self, exc_type, exc_val, exc_t):
        allura.config.middleware.make_app = self._make_app


@contextlib.contextmanager
def audits(*messages, **kwargs):
    """
    Asserts all the messages exist in audit log

    :param messages: regex strings
    :param bool user: if this is a user log

    """
    M.AuditLog.query.remove()
    yield
    if kwargs.get('user'):
        actor = kwargs.get('actor', '.*')
        ip_addr = kwargs.get('ip_addr', '.*')
        user_agent = kwargs.get('user_agent', '.*')
        preamble = f'(Done by user: {actor}\n)?IP Address: {ip_addr}\nUser-Agent: {user_agent}\n'
    else:
        preamble = ''

    for message in messages:
        found = M.AuditLog.query.find(dict(message=re.compile(preamble + message))).count()
        if not found:
            hints = ''
            all = M.AuditLog.query.find().all()
            if len(all) < 10:
                hints += '\nin these AuditLog messages:\n\t' + '\n\t'.join(a.message for a in all)
            if message != re.escape(message):
                hints += '\nYou may need to escape the regex chars in the text you are matching'
            raise AssertionError(f'Could not find "{message}"{hints}')


@contextlib.contextmanager
def out_audits(*messages, **kwargs):
    """
    Asserts none the messages exist in audit log.  "without audits"

    :param messages: list of regex strings
    :param bool user: if this is a user log

    """
    M.AuditLog.query.remove()
    yield
    if kwargs.get('user'):
        actor = kwargs.get('actor', '.*')
        ip_addr = kwargs.get('ip_addr', '.*')
        preamble = f'(Done by user: {actor}\n)?IP Address: {ip_addr}\n'
    else:
        preamble = ''
    for message in messages:
        assert not M.AuditLog.query.find(dict(
            message=re.compile(preamble + message))).count(), 'Found unexpected: "%s"' % message


# not a decorator but use it with LogCapture() context manager
def assert_logmsg(logs, msg, maxlevel=logging.CRITICAL+1):
    """
    can also use logs.check() or logs.check_present()
    :param testfixtures.logcapture.LogCapture logs: LogCapture() instance
    :param str msg: Message substring to look for
    """
    found_msg = False
    for r in logs.records:
        if msg in r.getMessage():
            found_msg = True
        if r.levelno > maxlevel:
            raise AssertionError(f'unexpected log {r.levelname} {r.getMessage()}')
    assert found_msg, \
        'Did not find "{}" in these logs: {}'.format(msg, '\n'.join([r.getMessage() for r in logs.records]))


def assert_logmsg_and_no_warnings_or_errors(logs, msg):
    """
    can also use logs.check() or logs.check_present()
    :param testfixtures.logcapture.LogCapture logs: LogCapture() instance
    :param str msg: Message substring to look for
    """
    return assert_logmsg(logs, msg, maxlevel=logging.INFO)


def assert_equivalent_urls(url1, url2):
    base1, _, qs1 = url1.partition('?')
    base2, _, qs2 = url2.partition('?')
    assert (
        (base1, parse_qs(qs1)) ==
        (base2, parse_qs(qs2)))
