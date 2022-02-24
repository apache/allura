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
import json
import hmac
import hashlib
import time
import socket
import ssl

import requests
from bson import ObjectId
from tg import expose, validate, redirect, flash, config
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c
from tg import response, request
from formencode import validators as fev, schema, Invalid
from ming.odm import session
from webob import exc
from pymongo.errors import DuplicateKeyError
from paste.deploy.converters import asint, aslist

from allura.app import AdminControllerMixin
from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.decorators import require_post, task
from allura.lib.utils import DateJSONEncoder
from allura import model as M
import six


log = logging.getLogger(__name__)


class WebhookValidator(fev.FancyValidator):
    def __init__(self, sender, app, **kw):
        self.app = app
        self.sender = sender
        super().__init__(**kw)

    def _to_python(self, value, state):
        wh = None
        if isinstance(value, M.Webhook):
            wh = value
        elif isinstance(value, ObjectId):
            wh = M.Webhook.query.get(_id=value)
        else:
            try:
                wh = M.Webhook.query.get(_id=ObjectId(value))
            except Exception:
                pass
        if wh and wh.type == self.sender.type and wh.app_config_id == self.app.config._id:
            return wh
        raise Invalid('Invalid webhook', value, state)


class WebhookCreateForm(schema.Schema):
    url = fev.URL(not_empty=True)
    secret = v.UnicodeString()


class WebhookEditForm(WebhookCreateForm):
    def __init__(self, sender, app):
        super().__init__()
        self.add_field('webhook', WebhookValidator(
            sender=sender, app=app, not_empty=True))


class WebhookControllerMeta(type):
    def __call__(cls, sender, app, *args, **kw):
        """Decorate post handlers with a validator that references
        the appropriate webhook sender for this controller.
        """
        if hasattr(cls, 'create'):
            cls.create = validate(
                cls.create_form(),
                error_handler=getattr(cls.index, '__func__', cls.index),
            )(cls.create)
        if hasattr(cls, 'edit'):
            cls.edit = validate(
                cls.edit_form(sender, app),
                error_handler=getattr(cls._default, '__func__', cls._default),
            )(cls.edit)
        return type.__call__(cls, sender, app, *args, **kw)


class WebhookController(BaseController, AdminControllerMixin, metaclass=WebhookControllerMeta):
    create_form = WebhookCreateForm
    edit_form = WebhookEditForm

    def __init__(self, sender, app):
        super().__init__()
        self.sender = sender()
        self.app = app

    def gen_secret(self):
        return h.cryptographic_nonce(20)

    def update_webhook(self, wh, url, secret=None):
        if not secret:
            secret = self.gen_secret()
        wh.hook_url = url
        wh.secret = secret
        try:
            session(wh).flush(wh)
        except DuplicateKeyError:
            session(wh).expunge(wh)
            msg = '_the_form: "{}" webhook already exists for {} {}'.format(
                wh.type, self.app.config.options.mount_label, url)
            raise Invalid(msg, None, None)

    @with_trailing_slash
    @expose('jinja:allura:templates/webhooks/create_form.html')
    def index(self, **kw):
        if not c.form_values and kw:
            # Executes if update_webhook raises an error
            c.form_values = {'url': kw.get('url'),
                             'secret': kw.get('secret')}
        return {'sender': self.sender,
                'action': 'create',
                'form': self.create_form()}

    @expose('jinja:allura:templates/webhooks/create_form.html')  # needed when we "return self.index(...)"
    @require_post()
    # @validate set dynamically in WebhookControllerMeta
    def create(self, url, secret):
        if self.sender.enforce_limit(self.app):
            webhook = M.Webhook(
                type=self.sender.type,
                app_config_id=self.app.config._id)
            try:
                self.update_webhook(webhook, url, secret)
            except Invalid as e:
                # trigger error_handler directly
                c.form_errors['_the_form'] = e
                return self.index(url=url, secret=secret)

            M.AuditLog.log('add webhook %s %s %s',
                           webhook.type, webhook.hook_url,
                           webhook.app_config.url())
            flash('Created successfully', 'ok')
        else:
            flash('You have exceeded the maximum number of webhooks '
                  'you are allowed to create for this project/app', 'error')
        redirect(self.app.admin_url + 'webhooks')

    @expose('jinja:allura:templates/webhooks/create_form.html')  # needed when we "return self._default(...)"
    @require_post()
    # @validate set dynamically in WebhookControllerMeta
    def edit(self, webhook, url, secret):
        old_url = webhook.hook_url
        old_secret = webhook.secret
        try:
            self.update_webhook(webhook, url, secret)
        except Invalid as e:
            # trigger error_handler directly
            c.form_errors['_the_form'] = e
            return self._default(webhook=webhook, url=url, secret=secret)
        M.AuditLog.log('edit webhook %s\n%s => %s\n%s',
                       webhook.type, old_url, url,
                       'secret changed' if old_secret != secret else '')
        flash('Edited successfully', 'ok')
        redirect(self.app.admin_url + 'webhooks')

    @expose('json:')
    @require_post()
    def delete(self, webhook, **kw):
        form = self.edit_form(self.sender, self.app)
        try:
            wh = form.fields['webhook'].to_python(webhook)
        except Invalid:
            raise exc.HTTPNotFound()
        wh.delete()
        M.AuditLog.log('delete webhook %s %s %s',
                       wh.type, wh.hook_url, wh.app_config.url())
        return {'status': 'ok'}

    @without_trailing_slash
    @expose('jinja:allura:templates/webhooks/create_form.html')
    def _default(self, webhook, **kw):
        form = self.edit_form(self.sender, self.app)
        try:
            wh = form.fields['webhook'].to_python(webhook)
        except Invalid:
            raise exc.HTTPNotFound()
        c.form_values = {'url': kw.get('url') or wh.hook_url,
                         'secret': kw.get('secret') or wh.secret,
                         'webhook': str(wh._id)}
        return {'sender': self.sender,
                'action': 'edit',
                'form': form}


class WebhookRestController(BaseController):
    def __init__(self, sender, app):
        super().__init__()
        self.sender = sender()
        self.app = app
        self.create_form = WebhookController.create_form
        self.edit_form = WebhookController.edit_form

    def _error(self, e):
        error = getattr(e, 'error_dict', None)
        if error:
            _error = {}
            for k, val in error.items():
                _error[k] = str(val)
            return _error
        error = getattr(e, 'msg', None)
        if not error:
            error = getattr(e, 'message', '')
        return error

    def update_webhook(self, wh, url, secret=None):
        controller = WebhookController(self.sender.__class__, self.app)
        controller.update_webhook(wh, url, secret)

    @expose('json:')
    @require_post()
    def index(self, **kw):
        response.content_type = 'application/json'
        try:
            params = {'secret': kw.pop('secret', ''),
                      'url': kw.pop('url', None)}
            valid = self.create_form().to_python(params)
        except Exception as e:
            response.status_int = 400
            return {'result': 'error', 'error': self._error(e)}
        if self.sender.enforce_limit(self.app):
            webhook = M.Webhook(
                type=self.sender.type,
                app_config_id=self.app.config._id)
            try:
                self.update_webhook(webhook, valid['url'], valid['secret'])
            except Invalid as e:
                response.status_int = 400
                return {'result': 'error', 'error': self._error(e)}
            M.AuditLog.log('add webhook %s %s %s',
                           webhook.type, webhook.hook_url,
                           webhook.app_config.url())
            response.status_int = 201
            # refetch updated values (e.g. mod_date)
            session(webhook).expunge(webhook)
            webhook = M.Webhook.query.get(_id=webhook._id)
            return webhook.__json__()
        else:
            limits = {
                'max': M.Webhook.max_hooks(
                    self.sender.type,
                    self.app.config.tool_name),
                'used': M.Webhook.query.find({
                    'type': self.sender.type,
                    'app_config_id': self.app.config._id,
                }).count(),
            }
            resp = {
                'result': 'error',
                'error': 'You have exceeded the maximum number of webhooks '
                         'you are allowed to create for this project/app',
                'limits': limits,
            }
            response.status_int = 400
            return resp

    @expose('json:')
    def _default(self, webhook, **kw):
        form = self.edit_form(self.sender, self.app)
        try:
            wh = form.fields['webhook'].to_python(webhook)
        except Invalid:
            raise exc.HTTPNotFound()
        if request.method == 'POST':
            return self._edit(wh, form, **kw)
        elif request.method == 'DELETE':
            return self._delete(wh)
        else:
            return wh.__json__()

    def _edit(self, webhook, form, **kw):
        old_secret = webhook.secret
        old_url = webhook.hook_url
        try:
            params = {'secret': kw.pop('secret', old_secret),
                      'url': kw.pop('url', old_url),
                      'webhook': str(webhook._id)}
            valid = form.to_python(params)
        except Exception as e:
            response.status_int = 400
            return {'result': 'error', 'error': self._error(e)}
        try:
            self.update_webhook(webhook, valid['url'], valid['secret'])
        except Invalid as e:
            response.status_int = 400
            return {'result': 'error', 'error': self._error(e)}
        M.AuditLog.log(
            'edit webhook %s\n%s => %s\n%s',
            webhook.type, old_url, valid['url'],
            'secret changed' if old_secret != valid['secret'] else '')
        # refetch updated values (e.g. mod_date)
        session(webhook).expunge(webhook)
        webhook = M.Webhook.query.get(_id=webhook._id)
        return webhook.__json__()

    def _delete(self, webhook):
        webhook.delete()
        M.AuditLog.log(
            'delete webhook %s %s %s',
            webhook.type,
            webhook.hook_url,
            webhook.app_config.url())
        return {'result': 'ok'}


class SendWebhookHelper:
    def __init__(self, webhook, payload):
        self.webhook = webhook
        self.payload = payload

    @property
    def timeout(self):
        return asint(config.get('webhook.timeout', 30))

    @property
    def retries(self):
        t = aslist(config.get('webhook.retry', [60, 120, 240]))
        return list(map(int, t))

    def sign(self, json_payload):
        signature = hmac.new(
            self.webhook.secret.encode('utf-8'),
            json_payload.encode('utf-8'),
            hashlib.sha1)
        return 'sha1=' + signature.hexdigest()

    def log_msg(self, msg, response=None):
        message = '{}: {} {} {}'.format(
            msg,
            self.webhook.type,
            self.webhook.hook_url,
            self.webhook.app_config.url())
        if response is not None:
            message = '{} {} {} {}'.format(
                message,
                response.status_code,
                response.text,
                response.headers)
        return message

    def send(self):
        json_payload = json.dumps(self.payload, cls=DateJSONEncoder)
        signature = self.sign(json_payload)
        headers = {'content-type': 'application/json',
                   'User-Agent': 'Allura Webhook (https://allura.apache.org/)',
                   'X-Allura-Signature': signature}
        ok = self._send(self.webhook.hook_url, json_payload, headers)
        if not ok:
            log.info('Retrying webhook in: %s', self.retries)
            for t in self.retries:
                log.info('Retrying webhook in %s seconds', t)
                time.sleep(t)
                ok = self._send(self.webhook.hook_url, json_payload, headers)
                if ok:
                    return

    def _send(self, url, data, headers):
        try:
            r = requests.post(
                url,
                data=data,
                headers=headers,
                timeout=self.timeout)
        except (requests.exceptions.RequestException,
                socket.timeout,
                ssl.SSLError):
            log.exception(self.log_msg('Webhook send error'))
            return False
        if r.status_code >= 200 and r.status_code < 300:
            log.info(self.log_msg('Webhook successfully sent'))
            return True
        else:
            log.error(self.log_msg('Webhook send error', response=r))
            return False


@task()
def send_webhook(webhook_id, payload):
    webhook = M.Webhook.query.get(_id=webhook_id)
    SendWebhookHelper(webhook, payload).send()


class WebhookSender:
    """Base class for webhook senders.

    Subclasses are required to implement :meth:`get_payload()` and set
    :attr:`type` and :attr:`triggered_by`.
    """

    type = None
    triggered_by = []
    controller = WebhookController
    api_controller = WebhookRestController

    def get_payload(self, **kw):
        """Return a dict with webhook payload"""
        raise NotImplementedError('get_payload')

    def send(self, params_or_list):
        """Post a task that will send webhook payload

        :param params_or_list: dict with keyword parameters to be passed to
            :meth:`get_payload` or a list of such dicts. If it's a list for each
            element appropriate payload will be submitted, but limit will be
            enforced only once for each webhook.
        """
        if not isinstance(params_or_list, list):
            params_or_list = [params_or_list]
        webhooks = M.Webhook.query.find(dict(
            app_config_id=c.app.config._id,
            type=self.type,
        )).all()
        if webhooks:
            payloads = [self.get_payload(**params)
                        for params in params_or_list]
            for webhook in webhooks:
                if webhook.enforce_limit():
                    webhook.update_limit()
                    for payload in payloads:
                        send_webhook.post(webhook._id, payload)
                else:
                    log.warn('Webhook fires too often: %s. Skipping', webhook)

    def enforce_limit(self, app):
        '''
        Checks if limit of webhooks created for given project/app is reached.
        Returns False if limit is reached, True otherwise.
        '''
        count = M.Webhook.query.find(dict(
            app_config_id=app.config._id,
            type=self.type,
        )).count()
        limit = M.Webhook.max_hooks(self.type, app.config.tool_name)
        return count < limit


class RepoPushWebhookSender(WebhookSender):
    type = 'repo-push'
    triggered_by = ['git', 'hg', 'svn']

    def _before(self, repo, commit_ids):
        if len(commit_ids) > 0:
            ci = commit_ids[-1]
            parents = repo.commit(ci).parent_ids
            if len(parents) > 0:
                # Merge commit will have multiple parents. As far as I can tell
                # the last one will be the branch head before merge
                return self._convert_id(parents[-1])
        return ''

    def _after(self, commit_ids):
        if len(commit_ids) > 0:
            return self._convert_id(commit_ids[0])
        return ''

    def _convert_id(self, _id):
        if ':' in _id:
            _id = 'r' + _id.rsplit(':', 1)[1]
        return _id

    def get_payload(self, commit_ids, **kw):
        app = kw.get('app') or c.app
        commits = [app.repo.commit(ci).webhook_info for ci in commit_ids]
        for ci in commits:
            ci['id'] = self._convert_id(ci['id'])
        before = self._before(app.repo, commit_ids)
        after = self._after(commit_ids)
        payload = {
            'size': len(commits),
            'commits': commits,
            'before': before,
            'after': after,
            'repository': {
                'name': app.config.options.mount_label,
                'full_name': app.url,
                'url': h.absurl(app.url),
            },
        }
        if kw.get('ref'):
            payload['ref'] = kw['ref']
        return payload
