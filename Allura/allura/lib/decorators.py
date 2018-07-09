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

import inspect
import sys
import json
import logging
from Cookie import Cookie
from collections import defaultdict
from urllib import unquote

from datetime import datetime

from datetime import timedelta
from decorator import decorator
from paste.deploy.converters import asint
from tg.decorators import before_validate
from tg import request, redirect, session, config
from tg.render import render
from webob import exc
from pylons import tmpl_context as c
from pylons import response
from webob.exc import HTTPFound, WSGIHTTPException

from allura.lib import helpers as h
from allura.lib import utils


log = logging.getLogger(__name__)


def task(*args, **kw):
    """Decorator that adds a ``.post()`` function to the decorated callable.

    Calling ``<original_callable>.post(*args, **kw)`` queues the callable for
    execution by a background worker process. All parameters must be
    BSON-serializable.

    Example usage::

        @task
        def myfunc():
            pass

        @task(notifications_disabled=True)
        def myotherfunc():
            # No email notifications will be sent for c.project during this task
            pass

    """
    def task_(func):
        def post(*args, **kwargs):
            delay = kwargs.pop('delay', 0)
            project = getattr(c, 'project', None)
            cm = (h.notifications_disabled if project and
                  kw.get('notifications_disabled') else h.null_contextmanager)
            with cm(project):
                from allura import model as M
                return M.MonQTask.post(func, args, kwargs, delay=delay)
        # if decorating a class, have to make it a staticmethod
        # or it gets a spurious cls argument
        func.post = staticmethod(post) if inspect.isclass(func) else post
        return func
    if len(args) == 1 and callable(args[0]):
        return task_(args[0])
    return task_


class event_handler(object):

    '''Decorator to register event handlers'''
    listeners = defaultdict(set)

    def __init__(self, *topics):
        self.topics = topics

    def __call__(self, func):
        for t in self.topics:
            self.listeners[t].add(func)
        return func


class require_post(object):
    '''
    A decorator to require controllers by accessed with a POST only.  Use whenever data will be modified by a
    controller, since that's what POST is good for.  We have CSRF protection middleware on POSTs, too.
    '''

    def __init__(self, redir=None):
        self.redir = redir

    def __call__(self, func):
        def check_method(remainder, params):
            if request.method != 'POST':
                if self.redir is not None:
                    redirect(self.redir)
                raise exc.HTTPMethodNotAllowed(headers={'Allow': 'POST'})
        before_validate(check_method)(func)
        return func


@decorator
def reconfirm_auth(func, *args, **kwargs):
    '''
    A decorator to require the user to reconfirm their login.  Useful for sensitive pages.
    '''
    from allura.lib.plugin import AuthenticationProvider

    if request.POST.get('password'):
        if AuthenticationProvider.get(request).validate_password(c.user, request.POST['password']):
            session['auth-reconfirmed'] = datetime.utcnow()
            session.save()
            kwargs.pop('password', None)
        else:
            c.form_errors['password'] = 'Invalid password.'

    allowed_timedelta = timedelta(seconds=asint(config.get('auth.reconfirm.seconds', 60)))
    last_reconfirm = session.get('auth-reconfirmed', datetime.min)
    if datetime.utcnow() - last_reconfirm <= allowed_timedelta:
        return func(*args, **kwargs)
    else:
        return render({}, 'jinja', "allura:templates/reconfirm_auth.html")


class log_action(object):  # pragma no cover

    def __init__(self,
                 logger=None,
                 level=logging.INFO,
                 msg=None,
                 *args, **kwargs):
        if logger is None:
            logger = logging
        self._logger = logger
        self._level = level
        self._msg = msg
        self._args = args
        self._kwargs = kwargs
        self._extra_proto = dict(
            user=None,
            user_id=None,
            source=None,
            project_name=None,
            group_id=None)

    def __call__(self, func):
        self._func = func
        self._extra_proto.update(action=func.__name__)
        if self._msg is None:
            self._msg = func.__name__
        result = lambda *args, **kwargs: self._wrapper(*args, **kwargs)
        # assert not hasattr(func, 'decoration')
        if hasattr(func, 'decoration'):
            result.decoration = func.decoration
        return result

    def _wrapper(self, *args, **kwargs):
        result = None
        try:
            try:
                result = self._func(*args, **kwargs)
            except exc.HTTPServerError:
                raise
            except exc.HTTPException, e:
                result = e
            args = self._args
            kwargs = self._kwargs
            extra = kwargs.setdefault('extra', {})
            extra.update(self._make_extra(result))
            self._logger.log(self._level, self._msg,
                             *self._args, **self._kwargs)
            return result
        except:
            args = self._args
            kwargs = self._kwargs
            extra = kwargs.setdefault('extra', {})
            extra.update(self._make_extra(result))
            kwargs['exc_info'] = sys.exc_info()
            self._logger.log(logging.ERROR, self._msg,
                             *self._args, **self._kwargs)
            raise

    def _make_extra(self, result=None):
        '''Create a dict of extra items to be added to a log record
        '''
        extra = self._extra_proto.copy()
        # Save the client IP address
        extra.update(client_ip=utils.ip_address(request))
        # Save the user info
        user = getattr(request, 'user', None)
        if user:
            extra.update(user=user.username,
                         user_id=user.id)
        # Save the project info
        if (result
                and isinstance(result, dict)
                and 'p' in result
                and result['p'] is not None):
            extra.update(
                source=result['p']['source'],
                project_name=result['p']['shortname'],
                group_id=result['p'].get('sf_id'))
        # Log the referer cookie if it exists
        referer_link = request.cookies.get('referer_link')
        if referer_link:
            referer_link = unquote(referer_link)
            try:
                referer_link = json.loads(referer_link)
            except ValueError:
                pass
        extra['referer_link'] = referer_link
        return extra


def getattr_(obj, name, default_thunk):
    "Similar to .setdefault in dictionaries."
    try:
        return getattr(obj, name)
    except AttributeError:
        default = default_thunk()
        setattr(obj, name, default)
        return default


@decorator
def memoize(func, *args):
    """
    Cache the method's result, for the given args
    """
    dic = getattr_(func, "memoize_dic", dict)
    # memoize_dic is created at the first call
    if args in dic:
        return dic[args]
    else:
        result = func(*args)
        dic[args] = result
        return result


def memorable_forget():
    """
    Decorator to mark a controller action as needing to "forget" remembered input values on the next
    page render, if we detect that the form post was processed successfully
    """

    def _ok_to_forget(response, controller_result, raised):
        """
        Look for signals that say it's probably ok to forget remembered inputs for the current form.
        Checks here will need to be expanded for controller actions that behave differently
        than others upon successful processing of their particular request
        """
        # if there is a flash message with status "ok", then we can forget.  If it is "error" we cannot.
        if response.headers:
            cookies = Cookie(response.headers.get('Set-Cookie', ''))
            if cookies and 'webflash' in cookies:
                webflash_value = json.loads(unquote(cookies['webflash'].value))
                if webflash_value['status'] == 'ok':
                    return True
                elif webflash_value['status'] == 'error':
                    return False

        # if the controller raised a 302, we can assume the value will be remembered by the app
        # if needed, and forget.
        if raised and isinstance(raised, HTTPFound):
            return True

        return False

    def forget(controller_result, raised=None):
        """
        Check if the form's inputs can be forgotten, and set the cookie to forget if so.
        :param res: the result of the controller action
        :param raised: any error (redirect or exception) raised by the controller action
        """
        if _ok_to_forget(response, controller_result, raised):
            response.set_cookie('memorable_forget', request.path)

    @decorator
    def _inner(func, *args, **kwargs):
        res, raised = (None, None)
        try:
            res = func(*args, **kwargs)
            forget(res)
            return res
        except WSGIHTTPException as ex:
            forget(None, ex)
            raise ex

    return _inner