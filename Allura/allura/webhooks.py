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

import requests
from bson import ObjectId
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import tmpl_context as c
from formencode import validators as fev, schema, Invalid
from ming.odm import session
from webob import exc
from pymongo.errors import DuplicateKeyError

from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib import validators as av
from allura.lib.decorators import require_post, task
from allura.lib.utils import DateJSONEncoder
from allura import model as M


log = logging.getLogger(__name__)


class MingOneOf(av.Ming):
    def __init__(self, ids, **kw):
        self.ids = ids
        super(MingOneOf, self).__init__(**kw)

    def _to_python(self, value, state):
        result = super(MingOneOf, self)._to_python(value, state)
        if result and result._id in self.ids:
            return result
        raise Invalid(
            u'Object must be one of: {}, not {}'.format(self.ids, value),
            value, state)


class WebhookValidator(fev.FancyValidator):
    def __init__(self, sender, ac_ids, **kw):
        self.ac_ids = ac_ids
        self.sender = sender
        super(WebhookValidator, self).__init__(**kw)

    def _to_python(self, value, state):
        wh = None
        if isinstance(value, M.Webhook):
            wh = value
        elif isinstance(value, ObjectId):
            wh = M.Webhook.query.get(_id=value)
        else:
            try:
                wh = M.Webhook.query.get(_id=ObjectId(value))
            except:
                pass
        if wh and wh.type == self.sender.type and wh.app_config_id in self.ac_ids:
            return wh
        raise Invalid(u'Invalid webhook', value, state)


class WebhookCreateForm(schema.Schema):
    def __init__(self, sender):
        super(WebhookCreateForm, self).__init__()
        self.triggered_by = [ac for ac in c.project.app_configs
                             if ac.tool_name.lower() in sender.triggered_by]
        self.add_field('app', MingOneOf(
            cls=M.AppConfig,
            ids=[ac._id for ac in self.triggered_by],
            not_empty=True))

    url = fev.URL(not_empty=True)
    secret = fev.UnicodeString()


class WebhookEditForm(WebhookCreateForm):
    def __init__(self, sender):
        super(WebhookEditForm, self).__init__(sender)
        self.add_field('webhook', WebhookValidator(
            sender=sender,
            ac_ids=[ac._id for ac in self.triggered_by],
            not_empty=True))


class WebhookControllerMeta(type):
    def __call__(cls, sender, *args, **kw):
        """Decorate post handlers with a validator that references
        the appropriate webhook sender for this controller.
        """
        if hasattr(cls, 'create'):
            cls.create = validate(
                cls.create_form(sender),
                error_handler=cls.index.__func__,
            )(cls.create)
        if hasattr(cls, 'edit'):
            cls.edit = validate(
                cls.edit_form(sender),
                error_handler=cls._default.__func__,
            )(cls.edit)
        return type.__call__(cls, sender, *args, **kw)


class WebhookController(BaseController):
    __metaclass__ = WebhookControllerMeta
    create_form = WebhookCreateForm
    edit_form = WebhookEditForm

    def __init__(self, sender):
        super(WebhookController, self).__init__()
        self.sender = sender

    def gen_secret(self):
        return h.cryptographic_nonce(20)

    def update_webhook(self, wh, url, ac, secret=None):
        if not secret:
            secret = self.gen_secret()
        wh.hook_url = url
        wh.app_config_id = ac._id
        wh.secret = secret
        try:
            session(wh).flush(wh)
        except DuplicateKeyError:
            session(wh).expunge(wh)
            msg = u'_the_form: "{}" webhook already exists for {} {}'.format(
                wh.type, ac.options.mount_label, url)
            raise Invalid(msg, None, None)

    def form_app_id(self, app):
        if app and isinstance(app, M.AppConfig):
            _app = unicode(app._id)
        elif app:
            _app = unicode(app)
        else:
            _app = None
        return _app

    @with_trailing_slash
    @expose('jinja:allura:templates/webhooks/create_form.html')
    def index(self, **kw):
        if not c.form_values and kw:
            # Executes if update_webhook raises an error
            _app = self.form_app_id(kw.get('app'))
            c.form_values = {'url': kw.get('url'),
                             'app': _app,
                             'secret': kw.get('secret')}
        return {'sender': self.sender,
                'action': 'create',
                'form': self.create_form(self.sender)}

    @expose()
    @require_post()
    def create(self, url, app, secret):
        wh = M.Webhook(type=self.sender.type)
        self.update_webhook(wh, url, app, secret)
        M.AuditLog.log('add webhook %s %s %s',
                       wh.type, wh.hook_url, wh.app_config.url())
        flash('Created successfully', 'ok')
        redirect(c.project.url() + 'admin/webhooks/')

    @expose()
    @require_post()
    def edit(self, webhook, url, app, secret):
        old_url = webhook.hook_url
        old_app = webhook.app_config.url()
        old_secret = webhook.secret
        self.update_webhook(webhook, url, app, secret)
        M.AuditLog.log('edit webhook %s\n%s => %s\n%s => %s\n%s',
            webhook.type, old_url, url, old_app, app.url(),
            'secret changed' if old_secret != secret else '')
        flash('Edited successfully', 'ok')
        redirect(c.project.url() + 'admin/webhooks/')

    @expose('json:')
    @require_post()
    def delete(self, webhook):
        form = self.edit_form(self.sender)
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
        form = self.edit_form(self.sender)
        try:
            wh = form.fields['webhook'].to_python(webhook)
        except Invalid:
            raise exc.HTTPNotFound()
        _app = self.form_app_id(kw.get('app')) or unicode(wh.app_config._id)
        c.form_values = {'url': kw.get('url') or wh.hook_url,
                         'app': _app,
                         'secret': kw.get('secret') or wh.secret,
                         'webhook': unicode(wh._id)}
        return {'sender': self.sender,
                'action': 'edit',
                'form': form}


@task()
def send_webhook(webhook_id, payload):
    webhook = M.Webhook.query.get(_id=webhook_id)
    url = webhook.hook_url
    json_payload = json.dumps(payload, cls=DateJSONEncoder)
    signature = hmac.new(
        webhook.secret.encode('utf-8'),
        json_payload.encode('utf-8'),
        hashlib.sha1)
    signature = 'sha1=' + signature.hexdigest()
    headers = {'content-type': 'application/json',
               'User-Agent': 'Allura Webhook (https://allura.apache.org/)',
               'X-Allura-Signature': signature}
    # TODO: catch
    # TODO: configurable timeout
    r = requests.post(url, data=json_payload, headers=headers, timeout=30)
    if r.status_code >= 200 and r.status_code <= 300:
        log.info('Webhook successfully sent: %s %s %s',
                 webhook.type, webhook.hook_url, webhook.app_config.url())
    else:
        # TODO: retry
        # TODO: configurable retries
        log.error('Webhook send error: %s %s %s %s %s',
                  webhook.type, webhook.hook_url,
                  webhook.app_config.url(),
                  r.status_code, r.reason)


class WebhookSender(object):
    """Base class for webhook senders.

    Subclasses are required to implement :meth:`get_payload()` and set
    :attr:`type` and :attr:`triggered_by`.
    """

    type = None
    triggered_by = []
    controller = WebhookController

    def get_payload(self, **kw):
        """Return a dict with webhook payload"""
        raise NotImplementedError('get_payload')

    def send(self, **kw):
        """Post a task that will send webhook payload"""
        webhooks = M.Webhook.query.find(dict(
            app_config_id=c.app.config._id,
            type=self.type,
        )).all()
        if webhooks:
            payload = self.get_payload(**kw)
            for webhook in webhooks:
                send_webhook.post(webhook._id, payload)


class RepoPushWebhookSender(WebhookSender):
    type = 'repo-push'
    triggered_by = ['git', 'hg', 'svn']

    def get_payload(self, commit_ids, **kw):
        app = kw.get('app') or c.app
        payload = {
            'url': h.absurl(app.url),
            'count': len(commit_ids),
            'revisions': [app.repo.commit(ci).info for ci in commit_ids],
        }
        return payload
