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

import requests
from bson import ObjectId
from tg import expose, validate, redirect
from tg.decorators import with_trailing_slash
from pylons import tmpl_context as c
from formencode import validators as fev, schema
from ming.odm import session

from allura.controllers import BaseController
from allura.lib import helpers as h
from allura.lib.decorators import require_post, task
from allura.lib.utils import DateJSONEncoder
from allura import model as M


log = logging.getLogger(__name__)


class WebhookCreateForm(schema.Schema):
    def __init__(self, hook):
        super(WebhookCreateForm, self).__init__()
        self.triggered_by = [ac for ac in c.project.app_configs
                             if ac.tool_name.lower() in hook.triggered_by]
        self.add_field('app', fev.OneOf(
            [unicode(ac._id) for ac in self.triggered_by]))

    url = fev.URL(not_empty=True)


class WebhookControllerMeta(type):
    def __call__(cls, hook, *args, **kw):
        """Decorate the `create` post handler with a validator that references
        the appropriate webhook sender for this controller.
        """
        if hasattr(cls, 'create'):
            cls.create = validate(
                cls.create_form(hook),
                error_handler=cls.index.__func__,
            )(cls.create)
        return type.__call__(cls, hook, *args, **kw)


class WebhookController(BaseController):
    __metaclass__ = WebhookControllerMeta
    create_form = WebhookCreateForm

    def __init__(self, hook):
        super(WebhookController, self).__init__()
        self.webhook = hook

    @with_trailing_slash
    @expose('jinja:allura:templates/webhooks/create_form.html')
    def index(self, **kw):
        return {'webhook': self.webhook,
                'form': self.create_form(self.webhook)}

    @expose()
    @require_post()
    def create(self, url, app):
        # TODO: catch DuplicateKeyError
        wh = M.Webhook(
            hook_url=url,
            app_config_id=ObjectId(app),
            type=self.webhook.type)
        session(wh).flush(wh)
        redirect(c.project.url() + 'admin/webhooks/')


@task()
def send_webhook(webhook_id, payload):
    webhook = M.Webhook.query.get(_id=webhook_id)
    url = webhook.hook_url
    headers = {'content-type': 'application/json'}
    json_payload = json.dumps(payload, cls=DateJSONEncoder)
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
