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
import hmac
import hashlib
import datetime as dt

from mock import Mock, MagicMock, patch, call
import pytest
from formencode import Invalid
from ming.odm import session
from tg import tmpl_context as c
from tg import config

from allura import model as M
from allura.lib import helpers as h
from allura.webhooks import (
    WebhookValidator,
    WebhookController,
    send_webhook,
    RepoPushWebhookSender,
    SendWebhookHelper,
)
from allura.tests import decorators as td
from alluratest.controller import (
    setup_basic_test,
    TestController,
    TestRestApiBase,
)
import six


# important to be distinct from 'test' and 'test2' which ForgeGit and
# ForgeImporter use, so that the tests can run in parallel and not clobber each
# other
test_project_with_repo = 'adobe-1'
with_git = td.with_tool(test_project_with_repo, 'git', 'src', 'Git')
with_git2 = td.with_tool(test_project_with_repo, 'git', 'src2', 'Git2')


class TestWebhookBase:
    def setup_method(self, method):
        setup_basic_test()
        self.patches = self.monkey_patch()
        for p in self.patches:
            p.start()
        self.setup_with_tools()
        self.project = M.Project.query.get(shortname=test_project_with_repo)
        self.git = self.project.app_instance('src')
        self.wh = M.Webhook(
            type='repo-push',
            app_config_id=self.git.config._id,
            hook_url='http://httpbin.org/post',
            secret='secret')
        session(self.wh).flush(self.wh)

    def teardown_method(self, method):
        for p in self.patches:
            p.stop()

    @with_git
    def setup_with_tools(self):
        pass

    def monkey_patch(self):
        # we don't need actual repo here, and this avoids test conflicts when
        # running in parallel
        repo_init = patch.object(M.Repository, 'init', autospec=True)
        return [repo_init]


class TestValidators(TestWebhookBase):
    @with_git2
    def test_webhook_validator(self):
        sender = Mock(type='repo-push')
        app = self.git
        invalid_app = self.project.app_instance('src2')
        v = WebhookValidator(sender=sender, app=app, not_empty=True)
        with pytest.raises(Invalid) as cm:
            v.to_python(None)
        assert cm.value.msg == 'Please enter a value'
        with pytest.raises(Invalid) as cm:
            v.to_python('invalid id')
        assert cm.value.msg == 'Invalid webhook'

        wh = M.Webhook(type='invalid type',
                       app_config_id=invalid_app.config._id,
                       hook_url='http://hooks.slack.com',
                       secret='secret')
        session(wh).flush(wh)
        # invalid type
        with pytest.raises(Invalid) as cm:
            v.to_python(wh._id)
        assert cm.value.msg == 'Invalid webhook'

        wh.type = 'repo-push'
        session(wh).flush(wh)
        # invalild app
        with pytest.raises(Invalid) as cm:
            v.to_python(wh._id)
        assert cm.value.msg == 'Invalid webhook'

        wh.app_config_id = app.config._id
        session(wh).flush(wh)
        assert v.to_python(wh._id) == wh
        assert v.to_python(str(wh._id)) == wh


class TestWebhookController(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self.patches = self.monkey_patch()
        for p in self.patches:
            p.start()
        self.setup_with_tools()
        self.project = M.Project.query.get(shortname=test_project_with_repo)
        self.git = self.project.app_instance('src')
        self.url = str(self.git.admin_url + 'webhooks')

    def teardown_method(self, method):
        super().teardown_method(method)
        for p in self.patches:
            p.stop()

    @with_git
    def setup_with_tools(self):
        pass

    def monkey_patch(self):
        gen_secret = patch.object(
            WebhookController,
            'gen_secret',
            return_value='super-secret',
            autospec=True)
        # we don't need actual repo here, and this avoids test conflicts when
        # running in parallel
        repo_init = patch.object(M.Repository, 'init', autospec=True)
        return [gen_secret, repo_init]

    def create_webhook(self, data, url=None):
        url = url or self.url
        r = self.app.post(url + '/repo-push/create', data)
        wf = json.loads(self.webflash(r))
        assert wf['status'] == 'ok'
        assert wf['message'] == 'Created successfully'
        return r

    def find_error(self, r, field, msg, form_type='create'):
        form = r.html.find('form', attrs={'action': form_type})
        if field == '_the_form':
            error = form.findPrevious('div', attrs={'class': 'error'})
        else:
            error = form.find('input', attrs={'name': field})
            error = error.findNext('div', attrs={'class': 'error'})
        if error:
            assert msg in error.getText()
        else:
            assert False, 'Validation error not found'

    def test_AAAA_WORKAROUND__edit(self):
        """
        This must run first in this test class for unknown reasons ever since
            https://github.com/TurboGears/tg2/commit/02fb49b14e70fdd8ac16973488fb3637e5e59114

        If any test runs the self.app.post from create_webhook before this one, then this test will fail on:
            with td.audits(msg):
                r = form.submit()
        because WebhookValidator's `value` will be "create" instead of an objectid str

        Maybe something to do with WebhookControllerMeta setup of `validate` decorators?
        """
        data1 = {'url': 'http://httpbin.org/post',
                 'secret': 'secret'}
        data2 = {'url': 'http://example.com/hook',
                 'secret': 'secret2'}
        self.create_webhook(data1).follow()
        self.create_webhook(data2).follow()
        assert M.Webhook.query.find().count() == 2
        wh1 = M.Webhook.query.get(hook_url=data1['url'])
        r = self.app.get(self.url + '/repo-push/%s' % wh1._id)
        form = r.forms[0]
        assert form['url'].value == data1['url']
        assert form['secret'].value == data1['secret']
        assert form['webhook'].value == str(wh1._id)
        form['url'] = 'http://host.org/hook'
        form['secret'] = 'new secret'
        msg = 'edit webhook repo-push\n{} => {}\n{}'.format(
            data1['url'], form['url'].value, 'secret changed')
        with td.audits(msg):
            r = form.submit()
        wf = json.loads(self.webflash(r))
        assert wf['status'] == 'ok'
        assert wf['message'] == 'Edited successfully'
        assert M.Webhook.query.find().count() == 2
        wh1 = M.Webhook.query.get(_id=wh1._id)
        assert wh1.hook_url == 'http://host.org/hook'
        assert wh1.app_config_id == self.git.config._id
        assert wh1.secret == 'new secret'
        assert wh1.type == 'repo-push'

        # Duplicates
        r = self.app.get(self.url + '/repo-push/%s' % wh1._id)
        form = r.forms[0]
        form['url'] = data2['url']
        r = form.submit()
        self.find_error(r, '_the_form',
                        '"repo-push" webhook already exists for Git http://example.com/hook',
                        form_type='edit')

    def test_access(self):
        self.app.get(self.url + '/repo-push/')
        self.app.get(self.url + '/repo-push/',
                     extra_environ={'username': 'test-user'},
                     status=403)
        r = self.app.get(self.url + '/repo-push/',
                         extra_environ={'username': '*anonymous'},
                         status=302)
        assert (r.location ==
                     'http://localhost/auth/'
                     '?return_to=%2Fadobe%2Fadobe-1%2Fadmin%2Fsrc%2Fwebhooks%2Frepo-push%2F')

    def test_invalid_hook_type(self):
        self.app.get(self.url + '/invalid-hook-type/', status=404)

    def test_create(self):
        assert M.Webhook.query.find().count() == 0
        r = self.app.get(self.url)
        assert '<h1>repo-push</h1>' in r
        assert 'http://httpbin.org/post' not in r
        data = {'url': 'http://httpbin.org/post',
                'secret': ''}
        msg = 'add webhook repo-push {} {}'.format(
            data['url'], self.git.config.url())
        with td.audits(msg):
            r = self.create_webhook(data).follow()
        assert 'http://httpbin.org/post' in r

        hooks = M.Webhook.query.find().all()
        assert len(hooks) == 1
        assert hooks[0].type == 'repo-push'
        assert hooks[0].hook_url == 'http://httpbin.org/post'
        assert hooks[0].app_config_id == self.git.config._id
        assert hooks[0].secret == 'super-secret'

        # Try to create duplicate
        with td.out_audits(msg):
            r = self.app.post(self.url + '/repo-push/create', data)
        self.find_error(r, '_the_form',
                        '"repo-push" webhook already exists for Git http://httpbin.org/post')
        assert M.Webhook.query.find().count() == 1

    def test_create_limit_reached(self):
        assert M.Webhook.query.find().count() == 0
        limit = json.dumps({'git': 1})
        with h.push_config(config, **{'webhook.repo_push.max_hooks': limit}):
            data = {'url': 'http://httpbin.org/post',
                    'secret': ''}
            r = self.create_webhook(data).follow()
            assert M.Webhook.query.find().count() == 1

            r = self.app.post(self.url + '/repo-push/create', data)
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert (
                wf['message'] ==
                'You have exceeded the maximum number of webhooks '
                'you are allowed to create for this project/app')
            assert M.Webhook.query.find().count() == 1

    def test_create_validation(self):
        assert M.Webhook.query.find().count() == 0
        r = self.app.post(
            self.url + '/repo-push/create', {}, status=404)

        data = {'url': '', 'secret': ''}
        r = self.app.post(self.url + '/repo-push/create', data)
        self.find_error(r, 'url', 'Please enter a value')

        data = {'url': 'qwer', 'secret': 'qwe'}
        r = self.app.post(self.url + '/repo-push/create', data)
        self.find_error(r, 'url',
                        'You must provide a full domain name (like qwer.com)')

    def test_edit_validation(self):
        invalid = M.Webhook(
            type='invalid type',
            app_config_id=None,
            hook_url='http://httpbin.org/post',
            secret='secret')
        session(invalid).flush(invalid)
        self.app.get(self.url + '/repo-push/%s' % invalid._id, status=404)

        data = {'url': 'http://httpbin.org/post',
                'secret': 'secret'}
        self.create_webhook(data).follow()
        wh = M.Webhook.query.get(hook_url=data['url'], type='repo-push')

        # invalid id in hidden field, just in case
        r = self.app.get(self.url + '/repo-push/%s' % wh._id)
        data = {k: v[0].value for (k, v) in r.forms[0].fields.items() if k}
        data['webhook'] = str(invalid._id)
        self.app.post(self.url + '/repo-push/edit', data, status=404)

        # empty values
        data = {'url': '', 'secret': '', 'webhook': str(wh._id)}
        r = self.app.post(self.url + '/repo-push/edit', data)
        self.find_error(r, 'url', 'Please enter a value', 'edit')

        data = {'url': 'qwe', 'secret': 'qwe', 'webhook': str(wh._id)}
        r = self.app.post(self.url + '/repo-push/edit', data)
        self.find_error(r, 'url',
                        'You must provide a full domain name (like qwe.com)', 'edit')

    def test_delete(self):
        data = {'url': 'http://httpbin.org/post',
                'secret': 'secret'}
        self.create_webhook(data).follow()
        assert M.Webhook.query.find().count() == 1
        wh = M.Webhook.query.get(hook_url=data['url'])
        data = {'webhook': str(wh._id)}
        msg = 'delete webhook repo-push {} {}'.format(
            wh.hook_url, self.git.config.url())
        with td.audits(msg):
            r = self.app.post(self.url + '/repo-push/delete', data)
        assert r.json == {'status': 'ok'}
        assert M.Webhook.query.find().count() == 0

    def test_delete_validation(self):
        invalid = M.Webhook(
            type='invalid type',
            app_config_id=None,
            hook_url='http://httpbin.org/post',
            secret='secret')
        session(invalid).flush(invalid)
        assert M.Webhook.query.find().count() == 1

        data = {'webhook': ''}
        self.app.post(self.url + '/repo-push/delete', data, status=404)

        data = {'webhook': str(invalid._id)}
        self.app.post(self.url + '/repo-push/delete', data, status=404)
        assert M.Webhook.query.find().count() == 1

    @with_git2
    def test_list_webhooks(self):
        git2 = self.project.app_instance('src2')
        url2 = str(git2.admin_url + 'webhooks')
        data1 = {'url': 'http://httpbin.org/post',
                 'secret': 'secret'}
        data2 = {'url': 'http://another-host.org/',
                 'secret': 'secret2'}
        data3 = {'url': 'http://another-app.org/',
                 'secret': 'secret3'}
        self.create_webhook(data1).follow()
        self.create_webhook(data2).follow()
        self.create_webhook(data3, url=url2).follow()
        wh1 = M.Webhook.query.get(hook_url=data1['url'])
        wh2 = M.Webhook.query.get(hook_url=data2['url'])

        r = self.app.get(self.url)
        assert '<h1>repo-push</h1>' in r
        rows = r.html.find('table').findAll('tr')
        assert len(rows) == 2
        rows = sorted((self._format_row(row) for row in rows), key=lambda rows: rows[0]['text'])
        expected_rows = sorted([
            [{'text': wh1.hook_url},
             {'text': wh1.secret},
             {'href': self.url + '/repo-push/' + str(wh1._id),
              'text': 'Edit'},
             {'href': self.url + '/repo-push/delete',
              'data-id': str(wh1._id)}],
            [{'text': wh2.hook_url},
             {'text': wh2.secret},
             {'href': self.url + '/repo-push/' + str(wh2._id),
              'text': 'Edit'},
             {'href': self.url + '/repo-push/delete',
              'data-id': str(wh2._id)}],
        ], key=lambda rows: rows[0]['text'])
        assert rows == expected_rows
        # make sure webhooks for another app is not visible
        assert 'http://another-app.org/' not in r
        assert 'secret3' not in r

    def _format_row(self, row):
        def link(td):
            a = td.find('a')
            return {'href': a.get('href'), 'text': a.getText()}

        def text(td):
            return {'text': td.getText()}

        def delete_btn(td):
            a = td.find('a')
            return {'href': a.get('href'), 'data-id': a.get('data-id')}

        tds = row.findAll('td')
        return [text(tds[0]), text(tds[1]), link(tds[2]), delete_btn(tds[3])]


class TestSendWebhookHelper(TestWebhookBase):
    def setup_method(self, method):
        super().setup_method(method)
        self.payload = {'some': ['data', 23]}
        self.h = SendWebhookHelper(self.wh, self.payload)

    def test_timeout(self):
        assert self.h.timeout == 30
        with h.push_config(config, **{'webhook.timeout': 10}):
            assert self.h.timeout == 10

    def test_retries(self):
        assert self.h.retries == [60, 120, 240]
        with h.push_config(config, **{'webhook.retry': '1 2 3 4 5 6'}):
            assert self.h.retries == [1, 2, 3, 4, 5, 6]

    def test_sign(self):
        json_payload = json.dumps(self.payload)
        signature = hmac.new(
            self.wh.secret.encode('utf-8'),
            json_payload.encode('utf-8'),
            hashlib.sha1)
        signature = 'sha1=' + signature.hexdigest()
        assert self.h.sign(json_payload) == signature

    def test_log_msg(self):
        assert (
            self.h.log_msg('OK') ==
            'OK: repo-push http://httpbin.org/post /adobe/adobe-1/src/')
        response = Mock(
            status_code=500,
            text='that is why',
            headers={'Content-Type': 'application/json'})
        assert (
            self.h.log_msg('Error', response=response) ==
            "Error: repo-push http://httpbin.org/post /adobe/adobe-1/src/ 500 "
            "that is why {'Content-Type': 'application/json'}")

    @patch('allura.webhooks.SendWebhookHelper', autospec=True)
    def test_send_webhook_task(self, swh):
        send_webhook(self.wh._id, self.payload)
        swh.assert_called_once_with(self.wh, self.payload)

    @patch('allura.webhooks.requests', autospec=True)
    @patch('allura.webhooks.log', autospec=True)
    def test_send(self, log, requests):
        requests.post.return_value = Mock(status_code=200)
        self.h.sign = Mock(return_value='sha1=abc')
        self.h.send()
        headers = {'content-type': 'application/json',
                   'User-Agent': 'Allura Webhook (https://allura.apache.org/)',
                   'X-Allura-Signature': 'sha1=abc'}
        requests.post.assert_called_once_with(
            self.wh.hook_url,
            data=json.dumps(self.payload),
            headers=headers,
            timeout=30)
        log.info.assert_called_once_with(
            'Webhook successfully sent: {} {} {}'.format(
                self.wh.type, self.wh.hook_url, self.wh.app_config.url()))

    @patch('allura.webhooks.time', autospec=True)
    @patch('allura.webhooks.requests', autospec=True)
    @patch('allura.webhooks.log', autospec=True)
    def test_send_error_response_status(self, log, requests, time):
        requests.post.return_value = Mock(status_code=500)
        self.h.send()
        assert requests.post.call_count == 4  # initial call + 3 retries
        assert (time.sleep.call_args_list ==
                     [call(60), call(120), call(240)])
        assert log.info.call_args_list == [
            call('Retrying webhook in: %s', [60, 120, 240]),
            call('Retrying webhook in %s seconds', 60),
            call('Retrying webhook in %s seconds', 120),
            call('Retrying webhook in %s seconds', 240)]
        assert log.error.call_count == 4
        log.error.assert_called_with(
            'Webhook send error: {} {} {} {} {} {}'.format(
                self.wh.type, self.wh.hook_url,
                self.wh.app_config.url(),
                requests.post.return_value.status_code,
                requests.post.return_value.text,
                requests.post.return_value.headers))

    @patch('allura.webhooks.time', autospec=True)
    @patch('allura.webhooks.requests', autospec=True)
    @patch('allura.webhooks.log', autospec=True)
    def test_send_error_no_retries(self, log, requests, time):
        requests.post.return_value = Mock(status_code=500)
        with h.push_config(config, **{'webhook.retry': ''}):
            self.h.send()
            assert requests.post.call_count == 1
            assert time.call_count == 0
            log.info.assert_called_once_with('Retrying webhook in: %s', [])
            assert log.error.call_count == 1
            log.error.assert_called_with(
                'Webhook send error: {} {} {} {} {} {}'.format(
                    self.wh.type, self.wh.hook_url,
                    self.wh.app_config.url(),
                    requests.post.return_value.status_code,
                    requests.post.return_value.text,
                    requests.post.return_value.headers))


class TestRepoPushWebhookSender(TestWebhookBase):
    @patch('allura.webhooks.send_webhook', autospec=True)
    def test_send(self, send_webhook):
        sender = RepoPushWebhookSender()
        sender.get_payload = Mock()
        with h.push_config(c, app=self.git):
            sender.send(dict(arg1=1, arg2=2))
        send_webhook.post.assert_called_once_with(
            self.wh._id,
            sender.get_payload.return_value)

    @patch('allura.webhooks.send_webhook', autospec=True)
    def test_send_with_list(self, send_webhook):
        sender = RepoPushWebhookSender()
        sender.get_payload = Mock(side_effect=[1, 2])
        self.wh.enforce_limit = Mock(return_value=True)
        with h.push_config(c, app=self.git):
            sender.send([dict(arg1=1, arg2=2), dict(arg1=3, arg2=4)])
        assert send_webhook.post.call_count == 2
        assert (send_webhook.post.call_args_list ==
                     [call(self.wh._id, 1), call(self.wh._id, 2)])
        assert self.wh.enforce_limit.call_count == 1

    @patch('allura.webhooks.log', autospec=True)
    @patch('allura.webhooks.send_webhook', autospec=True)
    def test_send_limit_reached(self, send_webhook, log):
        sender = RepoPushWebhookSender()
        sender.get_payload = Mock()
        self.wh.enforce_limit = Mock(return_value=False)
        with h.push_config(c, app=self.git):
            sender.send(dict(arg1=1, arg2=2))
        assert send_webhook.post.call_count == 0
        log.warn.assert_called_once_with(
            'Webhook fires too often: %s. Skipping', self.wh)

    @patch('allura.webhooks.send_webhook', autospec=True)
    def test_send_no_configured_webhooks(self, send_webhook):
        self.wh.delete()
        session(self.wh).flush(self.wh)
        sender = RepoPushWebhookSender()
        with h.push_config(c, app=self.git):
            sender.send(dict(arg1=1, arg2=2))
        assert send_webhook.post.call_count == 0

    def test_get_payload(self):
        sender = RepoPushWebhookSender()
        _ci = lambda x: MagicMock(webhook_info={'id': str(x)}, parent_ids=['0'])
        with patch.object(self.git.repo, 'commit', new=_ci):
            with h.push_config(c, app=self.git):
                result = sender.get_payload(commit_ids=['1', '2', '3'], ref='ref')
        expected_result = {
            'size': 3,
            'commits': [{'id': '1'}, {'id': '2'}, {'id': '3'}],
            'ref': 'ref',
            'after': '1',
            'before': '0',
            'repository': {
                'full_name': '/adobe/adobe-1/src/',
                'name': 'Git',
                'url': 'http://localhost/adobe/adobe-1/src/',
            },
        }
        assert result == expected_result

    def test_enforce_limit(self):
        def add_webhooks(suffix, n):
            for i in range(n):
                webhook = M.Webhook(
                    type='repo-push',
                    app_config_id=self.git.config._id,
                    hook_url=f'http://httpbin.org/{suffix}/{i}',
                    secret='secret')
                session(webhook).flush(webhook)

        sender = RepoPushWebhookSender()
        # default
        assert sender.enforce_limit(self.git) is True
        add_webhooks('one', 3)
        assert sender.enforce_limit(self.git) is False

        # config
        limit = json.dumps({'git': 5})
        with h.push_config(config, **{'webhook.repo_push.max_hooks': limit}):
            assert sender.enforce_limit(self.git) is True
            add_webhooks('two', 3)
            assert sender.enforce_limit(self.git) is False

    def test_before(self):
        sender = RepoPushWebhookSender()
        with patch.object(self.git.repo, 'commit', autospec=True) as _ci:
            assert sender._before(self.git.repo, ['3', '2', '1']) == ''
            _ci.return_value.parent_ids = ['0']
            assert sender._before(self.git.repo, ['3', '2', '1']) == '0'

    def test_after(self):
        sender = RepoPushWebhookSender()
        assert sender._after([]) == ''
        assert sender._after(['3', '2', '1']) == '3'

    def test_convert_id(self):
        sender = RepoPushWebhookSender()
        assert sender._convert_id('') == ''
        assert sender._convert_id('a433fa9') == 'a433fa9'
        assert sender._convert_id('a433fa9:13') == 'r13'


class TestModels(TestWebhookBase):
    def test_webhook_url(self):
        assert (self.wh.url() ==
                     f'/adobe/adobe-1/admin/src/webhooks/repo-push/{self.wh._id}')

    def test_webhook_enforce_limit(self):
        self.wh.last_sent = None
        assert self.wh.enforce_limit() is True
        # default value
        self.wh.last_sent = dt.datetime.utcnow() - dt.timedelta(seconds=31)
        assert self.wh.enforce_limit() is True
        self.wh.last_sent = dt.datetime.utcnow() - dt.timedelta(seconds=15)
        assert self.wh.enforce_limit() is False
        # value from config
        with h.push_config(config, **{'webhook.repo_push.limit': 100}):
            self.wh.last_sent = dt.datetime.utcnow() - dt.timedelta(seconds=101)
            assert self.wh.enforce_limit() is True
            self.wh.last_sent = dt.datetime.utcnow() - dt.timedelta(seconds=35)
            assert self.wh.enforce_limit() is False

    @patch('allura.model.webhook.dt', autospec=True)
    def test_update_limit(self, dt_mock):
        _now = dt.datetime(2015, 2, 2, 13, 39)
        dt_mock.datetime.utcnow.return_value = _now
        assert self.wh.last_sent is None
        self.wh.update_limit()
        session(self.wh).expunge(self.wh)
        assert M.Webhook.query.get(_id=self.wh._id).last_sent == _now

    def test_json(self):
        expected = {
            '_id': str(self.wh._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(self.wh._id),
            'type': 'repo-push',
            'hook_url': 'http://httpbin.org/post',
            'mod_date': self.wh.mod_date,
        }
        assert self.wh.__json__() == expected


class TestWebhookRestController(TestRestApiBase):
    def setup_method(self, method):
        super().setup_method(method)
        self.patches = self.monkey_patch()
        for p in self.patches:
            p.start()
        self.setup_with_tools()
        self.project = M.Project.query.get(shortname=test_project_with_repo)
        self.git = self.project.app_instance('src')
        self.url = '/rest' + self.git.admin_url + 'webhooks'
        self.webhooks = []
        for i in range(3):
            webhook = M.Webhook(
                type='repo-push',
                app_config_id=self.git.config._id,
                hook_url=f'http://httpbin.org/post/{i}',
                secret=f'secret-{i}')
            session(webhook).flush(webhook)
            self.webhooks.append(webhook)

    def teardown_method(self, method):
        super().teardown_method(method)
        for p in self.patches:
            p.stop()

    @with_git
    def setup_with_tools(self):
        pass

    def monkey_patch(self):
        gen_secret = patch.object(
            WebhookController,
            'gen_secret',
            return_value='super-secret',
            autospec=True)
        # we don't need actual repo here, and this avoids test conflicts when
        # running in parallel
        repo_init = patch.object(M.Repository, 'init', autospec=True)
        return [gen_secret, repo_init]

    def test_webhooks_list(self):
        r = self.api_get(self.url)
        webhooks = [{
            '_id': str(wh._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(wh._id),
            'type': 'repo-push',
            'hook_url': f'http://httpbin.org/post/{n}',
            'mod_date': str(wh.mod_date),
        } for n, wh in enumerate(self.webhooks)]
        expected = {
            'webhooks': webhooks,
            'limits': {'repo-push': {'max': 3, 'used': 3}},
        }
        assert r.json == expected

    def test_webhook_GET_404(self):
        r = self.api_get(self.url + '/repo-push/invalid', status=404)

    def test_webhook_GET(self):
        webhook = self.webhooks[0]
        r = self.api_get(f'{self.url}/repo-push/{webhook._id}')
        expected = {
            '_id': str(webhook._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(webhook._id),
            'type': 'repo-push',
            'hook_url': 'http://httpbin.org/post/0',
            'mod_date': str(webhook.mod_date),
        }
        assert r.status_int == 200
        assert r.json == expected

    def test_create_validation(self):
        assert M.Webhook.query.find().count() == len(self.webhooks)
        r = self.api_get(self.url + '/repo-push', status=405)

        r = self.api_post(self.url + '/repo-push', status=400)
        expected = {
            'result': 'error',
            'error': {'url': 'Please enter a value'},
        }
        assert r.json == expected

        data = {'url': 'qwer', 'secret': 'qwe'}
        r = self.api_post(self.url + '/repo-push', status=400, **data)
        expected = {
            'result': 'error',
            'error': {
                'url': 'You must provide a full domain name (like qwer.com)'
            },
        }
        assert r.json == expected
        assert M.Webhook.query.find().count() == len(self.webhooks)

    def test_create(self):
        assert M.Webhook.query.find().count() == len(self.webhooks)
        data = {'url': 'http://hook.slack.com/abcd'}
        limit = json.dumps({'git': 10})
        with h.push_config(config, **{'webhook.repo_push.max_hooks': limit}):
            msg = 'add webhook repo-push {} {}'.format(
                data['url'], self.git.config.url())
            with td.audits(msg):
                r = self.api_post(self.url + '/repo-push', status=201, **data)
        webhook = M.Webhook.query.get(hook_url=data['url'])
        assert webhook.secret == 'super-secret'  # secret generated
        expected = {
            '_id': str(webhook._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(webhook._id),
            'type': 'repo-push',
            'hook_url': data['url'],
            'mod_date': str(webhook.mod_date),
        }
        assert r.json == expected
        assert M.Webhook.query.find().count() == len(self.webhooks) + 1

    def test_create_duplicates(self):
        assert M.Webhook.query.find().count() == len(self.webhooks)
        data = {'url': self.webhooks[0].hook_url}
        limit = json.dumps({'git': 10})
        with h.push_config(config, **{'webhook.repo_push.max_hooks': limit}):
            r = self.api_post(self.url + '/repo-push', status=400, **data)
        expected = {'result': 'error',
                    'error': '_the_form: "repo-push" webhook already '
                              'exists for Git http://httpbin.org/post/0'}
        assert r.json == expected
        assert M.Webhook.query.find().count() == len(self.webhooks)

    def test_create_limit_reached(self):
        assert M.Webhook.query.find().count() == len(self.webhooks)
        data = {'url': 'http://hook.slack.com/abcd'}
        r = self.api_post(self.url + '/repo-push', status=400, **data)
        expected = {
            'result': 'error',
            'limits': {'max': 3, 'used': 3},
            'error': 'You have exceeded the maximum number of webhooks '
                      'you are allowed to create for this project/app'}
        assert r.json == expected
        assert M.Webhook.query.find().count() == len(self.webhooks)

    def test_edit_validation(self):
        webhook = self.webhooks[0]
        url = f'{self.url}/repo-push/{webhook._id}'
        data = {'url': 'qwe', 'secret': 'qwe'}
        r = self.api_post(url, status=400, **data)
        expected = {
            'result': 'error',
            'error': {
                'url': 'You must provide a full domain name (like qwe.com)'
            },
        }
        assert r.json == expected

    def test_edit(self):
        webhook = self.webhooks[0]
        url = f'{self.url}/repo-push/{webhook._id}'
        # change only url
        data = {'url': 'http://hook.slack.com/abcd'}
        msg = ('edit webhook repo-push\n'
               'http://httpbin.org/post/0 => http://hook.slack.com/abcd\n')
        with td.audits(msg):
            r = self.api_post(url, status=200, **data)
        webhook = M.Webhook.query.get(_id=webhook._id)
        assert webhook.hook_url == data['url']
        assert webhook.secret == 'secret-0'
        expected = {
            '_id': str(webhook._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(webhook._id),
            'type': 'repo-push',
            'hook_url': data['url'],
            'mod_date': str(webhook.mod_date),
        }
        assert r.json == expected

        # change only secret
        data = {'secret': 'new-secret'}
        msg = ('edit webhook repo-push\n'
               'http://hook.slack.com/abcd => http://hook.slack.com/abcd\n'
               'secret changed')
        with td.audits(msg):
            r = self.api_post(url, status=200, **data)
        webhook = M.Webhook.query.get(_id=webhook._id)
        assert webhook.hook_url == 'http://hook.slack.com/abcd'
        assert webhook.secret == 'new-secret'
        expected = {
            '_id': str(webhook._id),
            'url': 'http://localhost/rest/adobe/adobe-1/admin'
                   '/src/webhooks/repo-push/{}'.format(webhook._id),
            'type': 'repo-push',
            'hook_url': 'http://hook.slack.com/abcd',
            'mod_date': str(webhook.mod_date),
        }
        assert r.json == expected

    def test_edit_duplicates(self):
        webhook = self.webhooks[0]
        url = f'{self.url}/repo-push/{webhook._id}'
        data = {'url': 'http://httpbin.org/post/1'}
        r = self.api_post(url, status=400, **data)
        expected = {'result': 'error',
                    'error': '_the_form: "repo-push" webhook already '
                              'exists for Git http://httpbin.org/post/1'}
        assert r.json == expected

    def test_delete_validation(self):
        url = f'{self.url}/repo-push/invalid'
        self.api_delete(url, status=404)

    def test_delete(self):
        assert M.Webhook.query.find().count() == 3
        webhook = self.webhooks[0]
        url = f'{self.url}/repo-push/{webhook._id}'
        msg = 'delete webhook repo-push {} {}'.format(
            webhook.hook_url, self.git.config.url())
        with td.audits(msg):
            r = self.api_delete(url, status=200)
        assert r.json == {'result': 'ok'}
        assert M.Webhook.query.find().count() == 2
        assert M.Webhook.query.get(_id=webhook._id) is None

    def test_permissions(self):
        self.api_get(self.url, user='test-user', status=403)
        self.api_get(self.url, user='*anonymous', status=401)
        url = self.url + '/repo-push/'
        self.api_post(url, user='test-user', status=403)
        self.api_post(url, user='*anonymous', status=401)
        url = self.url + '/repo-push/' + str(self.webhooks[0]._id)
        self.api_get(url, user='test-user', status=403)
        self.api_get(url, user='*anonymous', status=401)
        self.api_post(url, user='test-user', status=403)
        self.api_post(url, user='*anonymous', status=401)
        self.api_delete(url, user='test-user', status=403)
        self.api_delete(url, user='*anonymous', status=401)
