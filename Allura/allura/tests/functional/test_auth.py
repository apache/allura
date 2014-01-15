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

from datetime import datetime, time, timedelta
import re
import json
from bson import ObjectId
from urlparse import urlparse, parse_qs

import mock
from nose.tools import (
    assert_equal,
    assert_not_equal,
    assert_is_none,
    assert_is_not_none,
    assert_in,
    assert_true
)
from pylons import tmpl_context as c
from allura.tests import TestController
from allura.tests import decorators as td
from allura import model as M
from ming.orm.ormsession import ThreadLocalORMSession, session
from allura.lib import oid_helper
from tg import config
from mock import patch
from allura.lib import plugin


def unentity(s):
    return s.replace('&quot;', '"')


class TestAuth(TestController):

    def test_login(self):
        self.app.get('/auth/')
        r = self.app.post('/auth/send_verification_link',
                          params=dict(a='test@example.com'))
        email = M.User.query.get(username='test-admin').email_addresses[0]
        r = self.app.post('/auth/send_verification_link', params=dict(a=email))
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/auth/verify_addr', params=dict(a='foo'))
        assert json.loads(self.webflash(r))[
            'status'] == 'error', self.webflash(r)
        ea = M.EmailAddress.query.find().first()
        r = self.app.get('/auth/verify_addr', params=dict(a=ea.nonce))
        assert json.loads(self.webflash(r))['status'] == 'ok', self.webflash(r)
        r = self.app.get('/auth/logout')
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='foo'))
        r = self.app.post('/auth/do_login', params=dict(
            username='test-user', password='food'))
        assert 'Invalid login' in str(r), r.showbrowser()
        r = self.app.post('/auth/do_login', params=dict(
            username='test-usera', password='foo'))
        assert 'Invalid login' in str(r), r.showbrowser()

    @td.with_user_project('test-admin')
    def test_prefs(self):
        r = self.app.get('/auth/preferences/',
                         extra_environ=dict(username='test-admin'))
        # check preconditions of test data
        assert 'test@example.com' not in r
        assert 'test-admin@users.localhost' in r
        assert_equal(M.User.query.get(username='test-admin').get_pref('email_address'),
                     'test-admin@users.localhost')

        # add test@example
        r = self.app.post('/auth/preferences/update', params={
            'preferences.display_name': 'Test Admin',
            'new_addr.addr': 'test@example.com',
            'new_addr.claim': 'Claim Address',
            'primary_addr': 'test-admin@users.localhost',
            'preferences.email_format': 'plain'},
            extra_environ=dict(username='test-admin'))
        r = self.app.get('/auth/preferences/')
        assert 'test@example.com' in r
        assert_equal(M.User.query.get(username='test-admin').get_pref('email_address'),
                     'test-admin@users.localhost')

        # remove test-admin@users.localhost
        r = self.app.post('/auth/preferences/update', params={
            'preferences.display_name': 'Test Admin',
            'addr-1.ord': '1',
            'addr-1.delete': 'on',
            'addr-2.ord': '2',
            'new_addr.addr': '',
            'primary_addr': 'test-admin@users.localhost',
            'preferences.email_format': 'plain'},
            extra_environ=dict(username='test-admin'))
        r = self.app.get('/auth/preferences/')
        assert 'test-admin@users.localhost' not in r
        # preferred address has changed to remaining address
        assert_equal(M.User.query.get(username='test-admin').get_pref('email_address'),
                     'test@example.com')

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions(self):
        r = self.app.get('/auth/subscriptions/',
                         extra_environ=dict(username='test-admin'))
        subscriptions = M.Mailbox.query.find(dict(
            user_id=c.user._id, is_flash=False)).all()
        # make sure page actually lists all the user's subscriptions
        assert len(
            subscriptions) > 0, 'Test user has no subscriptions, cannot verify that they are shown'
        for m in subscriptions:
            assert m._id in r, "Page doesn't list subscription for Mailbox._id = %s" % m._id

        # make sure page lists all tools which user can subscribe
        user = M.User.query.get(username='test-admin')
        tools = []
        for p in user.my_projects():
            for ac in p.app_configs:
                if not M.Mailbox.subscribed(project_id=p._id, app_config_id=ac._id):
                    tools.append(ac._id)
        for tool_id in tools:
            assert tool_id in r, "Page doesn't list tool with app_config_id = %s" % tool_id

    def _find_subscriptions_form(self, r):
        form = None
        for f in r.forms.itervalues():
            if f.action == 'update_subscriptions':
                form = f
                break
        assert form is not None, "Can't find subscriptions form"
        return form

    def _find_subscriptions_field(self, form, subscribed=False):
        field_name = None
        for k, v in form.fields.iteritems():
            if subscribed:
                check = c and v[0].value == 'on'
            else:
                check = c and v[0].value != 'on'
            if k and k.endswith('.subscribed') and check:
                field_name = k.replace('.subscribed', '')
        assert field_name, "Can't find unsubscribed tool for user"
        return field_name

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions_subscribe(self):
        resp = self.app.get('/auth/subscriptions/',
                            extra_environ=dict(username='test-admin'))
        form = self._find_subscriptions_form(resp)
        # find not subscribed tool, subscribe and verify
        field_name = self._find_subscriptions_field(form, subscribed=False)
        t_id = ObjectId(form.fields[field_name + '.tool_id'][0].value)
        p_id = ObjectId(form.fields[field_name + '.project_id'][0].value)
        subscribed = M.Mailbox.subscribed(project_id=p_id, app_config_id=t_id)
        assert not subscribed, "User already subscribed for tool %s" % t_id
        form.fields[field_name + '.subscribed'][0].value = 'on'
        form.submit()
        subscribed = M.Mailbox.subscribed(project_id=p_id, app_config_id=t_id)
        assert subscribed, "User is not subscribed for tool %s" % t_id

    @td.with_user_project('test-admin')
    def test_prefs_subscriptions_unsubscribe(self):
        resp = self.app.get('/auth/subscriptions/',
                            extra_environ=dict(username='test-admin'))
        form = self._find_subscriptions_form(resp)
        field_name = self._find_subscriptions_field(form, subscribed=True)
        s_id = ObjectId(form.fields[field_name + '.subscription_id'][0].value)
        s = M.Mailbox.query.get(_id=s_id)
        assert s, "User has not subscription with Mailbox._id = %s" % s_id
        form.fields[field_name + '.subscribed'][0].value = None
        form.submit()
        s = M.Mailbox.query.get(_id=s_id)
        assert not s, "User still has subscription with Mailbox._id %s" % s_id

    def test_format_email(self):
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'html', 'subscriptions': ''})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="html">HTML</option>' in r
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'plain', 'subscriptions': ''})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="plain">Plain Text</option>' in r
        self.app.post('/auth/subscriptions/update_subscriptions',
                      params={'email_format': 'both', 'subscriptions': ''})
        r = self.app.get('/auth/subscriptions/')
        assert '<option selected value="both">Combined</option>' in r

    def test_api_key(self):
        r = self.app.get('/auth/preferences/')
        assert 'No API token generated' in r
        r = self.app.post('/auth/preferences/gen_api_token', status=302)
        r = self.app.get('/auth/preferences/')
        assert 'No API token generated' not in r
        assert 'API Key:' in r
        assert 'Secret Key:' in r
        r = self.app.post('/auth/preferences/del_api_token', status=302)
        r = self.app.get('/auth/preferences/')
        assert 'No API token generated' in r

    @mock.patch('allura.controllers.auth.verify_oid')
    def test_login_verify_oid_with_provider(self, verify_oid):
        verify_oid.return_value = dict()
        self.app.get('/auth/login_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=200)
        verify_oid.assert_called_with('http://www.google.com/accounts/o8/id',
                                      failure_redirect='.',
                                      return_to='login_process_oid?return_to=None',
                                      title='OpenID Login',
                                      prompt='Click below to continue')

    @mock.patch('allura.controllers.auth.verify_oid')
    def test_login_verify_oid_without_provider(self, verify_oid):
        verify_oid.return_value = dict()
        self.app.get('/auth/login_verify_oid', params=dict(
            provider='', username='rick446@usa.net'),
            status=200)
        verify_oid.assert_called_with('rick446@usa.net',
                                      failure_redirect='.',
                                      return_to='login_process_oid?return_to=None',
                                      title='OpenID Login',
                                      prompt='Click below to continue')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_login_verify_oid_good_provider_no_redirect(self, Consumer):
        Consumer().begin().shouldSendRedirect.return_value = False
        Consumer().begin().formMarkup.return_value = "<!-- I'm a mock object! -->"
        result = self.app.get('/auth/login_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=200)
        flash = self.webflash(result)
        assert_equal(flash, '')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_login_verify_oid_good_provider_redirect(self, Consumer):
        Consumer().begin().shouldSendRedirect.return_value = True
        Consumer().begin().redirectURL.return_value = 'http://some.url/'
        result = self.app.get('/auth/login_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=302)
        assert_equal(result.headers['Location'], 'http://some.url/')
        flash = self.webflash(result)
        assert_equal(flash, '')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_login_verify_oid_bad_provider(self, Consumer):
        Consumer().begin.side_effect = oid_helper.consumer.DiscoveryFailure(
            'bad', mock.Mock('response'))
        result = self.app.get('/auth/login_verify_oid', params=dict(
            provider='http://www.google.com/accounts/', username='rick446@usa.net'),
            status=302)
        flash = self.webflash(result)
        assert_equal(flash, '{"status": "error", "message": "bad"}')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_login_verify_oid_bad_provider2(self, Consumer):
        Consumer().begin.return_value = None
        result = self.app.get('/auth/login_verify_oid', params=dict(
            provider='http://www.google.com/accounts/', username='rick446@usa.net'),
            status=302)
        flash = self.webflash(result)
        assert_equal(
            flash, '{"status": "error", "message": "No openid services found for <code>http://www.google.com/accounts/</code>"}')

    @mock.patch('allura.controllers.auth.verify_oid')
    def test_claim_verify_oid_with_provider(self, verify_oid):
        verify_oid.return_value = dict()
        self.app.get('/auth/claim_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=200)
        verify_oid.assert_called_with('http://www.google.com/accounts/o8/id',
                                      failure_redirect='claim_oid',
                                      return_to='claim_process_oid',
                                      title='Claim OpenID',
                                      prompt='Click below to continue')

    @mock.patch('allura.controllers.auth.verify_oid')
    def test_claim_verify_oid_without_provider(self, verify_oid):
        verify_oid.return_value = dict()
        self.app.get('/auth/claim_verify_oid', params=dict(
            provider='', username='rick446@usa.net'),
            status=200)
        verify_oid.assert_called_with('rick446@usa.net',
                                      failure_redirect='claim_oid',
                                      return_to='claim_process_oid',
                                      title='Claim OpenID',
                                      prompt='Click below to continue')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_claim_verify_oid_good_provider_no_redirect(self, Consumer):
        Consumer().begin().shouldSendRedirect.return_value = False
        Consumer().begin().formMarkup.return_value = "<!-- I'm a mock object! -->"
        result = self.app.get('/auth/claim_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=200)
        flash = self.webflash(result)
        assert_equal(flash, '')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_claim_verify_oid_good_provider_redirect(self, Consumer):
        Consumer().begin().shouldSendRedirect.return_value = True
        Consumer().begin().redirectURL.return_value = 'http://some.url/'
        result = self.app.get('/auth/claim_verify_oid', params=dict(
            provider='http://www.google.com/accounts/o8/id', username='rick446@usa.net'),
            status=302)
        assert_equal(result.headers['Location'], 'http://some.url/')
        flash = self.webflash(result)
        assert_equal(flash, '')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_claim_verify_oid_bad_provider(self, Consumer):
        Consumer().begin.side_effect = oid_helper.consumer.DiscoveryFailure(
            'bad', mock.Mock('response'))
        result = self.app.get('/auth/claim_verify_oid', params=dict(
            provider='http://www.google.com/accounts/', username='rick446@usa.net'),
            status=302)
        flash = self.webflash(result)
        assert_equal(flash, '{"status": "error", "message": "bad"}')

    @mock.patch('allura.lib.oid_helper.consumer.Consumer')
    def test_claim_verify_oid_bad_provider2(self, Consumer):
        Consumer().begin.return_value = None
        result = self.app.get('/auth/claim_verify_oid', params=dict(
            provider='http://www.google.com/accounts/', username='rick446@usa.net'),
            status=302)
        flash = self.webflash(result)
        assert_equal(
            flash, '{"status": "error", "message": "No openid services found for <code>http://www.google.com/accounts/</code>"}')

    def test_setup_openid_user_current_user(self):
        r = self.app.get('/auth/setup_openid_user')
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
            username='test-admin', display_name='Test Admin'))
        flash = self.webflash(r)
        assert_equal(
            flash, '{"status": "ok", "message": "Your username has been set to test-admin."}')

    def test_setup_openid_user_taken_user(self):
        r = self.app.get('/auth/setup_openid_user')
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
            username='test-user', display_name='Test User'))
        flash = self.webflash(r)
        assert_equal(
            flash, '{"status": "error", "message": "That username is already taken.  Please choose another."}')

    def test_setup_openid_user_new_user(self):
        r = self.app.get('/auth/setup_openid_user')
        r = self.app.post('/auth/do_setup_openid_user', params=dict(
            username='test-alkajs', display_name='Test Alkajs'))
        flash = self.webflash(r)
        assert_equal(
            flash, '{"status": "ok", "message": "Your username has been set to test-alkajs."}')

    def test_create_account(self):
        r = self.app.get('/auth/create_account')
        assert 'Create an Account' in r
        r = self.app.post('/auth/save_new',
                          params=dict(username='aaa', pw='123'))
        assert 'Enter a value 8 characters long or more' in r
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me'))
        r = r.follow()
        assert 'User "Test Me" registered' in unentity(r.body)
        r = self.app.post(
            '/auth/save_new',
            params=dict(
                username='aaa',
                pw='12345678',
                pw2='12345678',
                display_name='Test Me'))
        assert 'That username is already taken. Please choose another.' in r
        r = self.app.get('/auth/logout')
        r = self.app.post(
            '/auth/do_login',
            params=dict(username='aaa', password='12345678'),
            status=302)

    def test_one_project_role(self):
        """Make sure when a user goes to a new project only one project role is created.
           There was an issue with extra project roles getting created if a user went directly to
           an admin page."""
        p_nbhd = M.Neighborhood.query.get(name='Projects')
        p = M.Project.query.get(shortname='test', neighborhood_id=p_nbhd._id)
        self.app.post('/auth/save_new', params=dict(
            username='aaa',
            pw='12345678',
            pw2='12345678',
            display_name='Test Me')).follow()
        user = M.User.query.get(username='aaa')
        assert M.ProjectRole.query.find(
            dict(user_id=user._id, project_id=p._id)).count() == 0
        self.app.get('/p/test/admin/permissions',
                         extra_environ=dict(username='aaa'), status=403)
        assert M.ProjectRole.query.find(
            dict(user_id=user._id, project_id=p._id)).count() <= 1

    def test_default_lookup(self):
        # Make sure that default _lookup() throws 404
        self.app.get('/auth/foobar', status=404)

    def test_disabled_user(self):
        user = M.User.query.get(username='test-admin')
        sess = session(user)
        assert not user.disabled
        r = self.app.get('/p/test/admin/',
                         extra_environ={'username': 'test-admin'})
        assert_equal(r.status_int, 200, 'Redirect to %s' % r.location)
        user.disabled = True
        sess.save(user)
        sess.flush()
        user = M.User.query.get(username='test-admin')
        assert user.disabled
        r = self.app.get('/p/test/admin/',
                         extra_environ={'username': 'test-admin'})
        assert_equal(r.status_int, 302)
        assert_equal(r.location,
                     'http://localhost/auth/?return_to=%2Fp%2Ftest%2Fadmin%2F')


class TestPreferences(TestController):

    @td.with_user_project('test-admin')
    def test_personal_data(self):
        from pytz import country_names
        setsex, setbirthdate, setcountry, setcity, settimezone = \
            ('Male', '19/08/1988', 'IT', 'Milan', 'Europe/Rome')
        self.app.get('/auth/user_info/')

        # Check if personal data is properly set
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(
                              sex=setsex,
                              birthdate=setbirthdate,
                              country=setcountry,
                              city=setcity,
                              timezone=settimezone))
        user = M.User.query.get(username='test-admin')
        sex = user.sex
        assert sex == setsex
        birthdate = user.birthdate.strftime('%d/%m/%Y')
        assert birthdate == setbirthdate
        country = user.localization.country
        assert country_names.get(setcountry) == country
        city = user.localization.city
        assert city == setcity
        timezone = user.timezone
        assert timezone == settimezone

        # Check if setting a wrong date everything works correctly
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(birthdate='30/02/1998'))
        assert 'Please enter a valid date' in str(r)
        user = M.User.query.get(username='test-admin')
        sex = user.sex
        assert sex == setsex
        birthdate = user.birthdate.strftime('%d/%m/%Y')
        assert birthdate == setbirthdate
        country = user.localization.country
        assert country_names.get(setcountry) == country
        city = user.localization.city
        assert city == setcity
        timezone = user.timezone
        assert timezone == settimezone

        # Check deleting birthdate
        r = self.app.post('/auth/user_info/change_personal_data',
                          params=dict(
                              sex=setsex,
                              birthdate='',
                              country=setcountry,
                              city=setcity,
                              timezone=settimezone))
        user = M.User.query.get(username='test-admin')
        assert user.birthdate is None

    @td.with_user_project('test-admin')
    def test_contacts(self):
        # Add skype account
        testvalue = 'testaccount'
        self.app.get('/auth/user_info/contacts/')
        self.app.post('/auth/user_info/contacts/skype_account',
                          params=dict(skypeaccount=testvalue))
        user = M.User.query.get(username='test-admin')
        assert user.skypeaccount == testvalue

        # Add social network account
        socialnetwork = 'Facebook'
        accounturl = 'http://www.facebook.com/test'
        self.app.post('/auth/user_info/contacts/add_social_network',
                          params=dict(socialnetwork=socialnetwork,
                                      accounturl=accounturl))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1 and \
            user.socialnetworks[0].socialnetwork == socialnetwork and \
            user.socialnetworks[0].accounturl == accounturl

        # Add second social network account
        socialnetwork2 = 'Twitter'
        accounturl2 = 'http://twitter.com/test'
        self.app.post('/auth/user_info/contacts/add_social_network',
                          params=dict(socialnetwork=socialnetwork2,
                                      accounturl='@test'))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 2 and \
            ({'socialnetwork': socialnetwork, 'accounturl': accounturl} in user.socialnetworks and
             {'socialnetwork': socialnetwork2, 'accounturl': accounturl2} in user.socialnetworks)

        # Remove first social network account
        self.app.post('/auth/user_info/contacts/remove_social_network',
                          params=dict(socialnetwork=socialnetwork,
                                      account=accounturl))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1 and \
            {'socialnetwork': socialnetwork2, 'accounturl':
             accounturl2} in user.socialnetworks

        # Add empty social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                          params=dict(accounturl=accounturl, socialnetwork=''))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1 and \
            {'socialnetwork': socialnetwork2, 'accounturl':
             accounturl2} in user.socialnetworks

        # Add invalid social network account
        self.app.post('/auth/user_info/contacts/add_social_network',
                          params=dict(accounturl=accounturl, socialnetwork='invalid'))
        user = M.User.query.get(username='test-admin')
        assert len(user.socialnetworks) == 1 and \
            {'socialnetwork': socialnetwork2, 'accounturl':
             accounturl2} in user.socialnetworks

        # Add telephone number
        telnumber = '+3902123456'
        self.app.post('/auth/user_info/contacts/add_telnumber',
                          params=dict(newnumber=telnumber))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers)
                == 1 and (user.telnumbers[0] == telnumber))

        # Add second telephone number
        telnumber2 = '+3902654321'
        self.app.post('/auth/user_info/contacts/add_telnumber',
                          params=dict(newnumber=telnumber2))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers)
                == 2 and telnumber in user.telnumbers and telnumber2 in user.telnumbers)

        # Remove first telephone number
        self.app.post('/auth/user_info/contacts/remove_telnumber',
                          params=dict(oldvalue=telnumber))
        user = M.User.query.get(username='test-admin')
        assert (len(user.telnumbers) == 1 and telnumber2 in user.telnumbers)

        # Add website
        website = 'http://www.testurl.com'
        self.app.post('/auth/user_info/contacts/add_webpage',
                          params=dict(newwebsite=website))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages) == 1 and (website in user.webpages))

        # Add second website
        website2 = 'http://www.testurl2.com'
        self.app.post('/auth/user_info/contacts/add_webpage',
                          params=dict(newwebsite=website2))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages)
                == 2 and website in user.webpages and website2 in user.webpages)

        # Remove first website
        self.app.post('/auth/user_info/contacts/remove_webpage',
                          params=dict(oldvalue=website))
        user = M.User.query.get(username='test-admin')
        assert (len(user.webpages) == 1 and website2 in user.webpages)

    @td.with_user_project('test-admin')
    def test_availability(self):
        # Add availability timeslot
        weekday = 'Monday'
        starttime = time(9, 0, 0)
        endtime = time(12, 0, 0)

        self.app.get('/auth/user_info/availability/')
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday,
                              starttime=starttime.strftime('%H:%M'),
                              endtime=endtime.strftime('%H:%M')))
        user = M.User.query.get(username='test-admin')
        timeslot1dict = dict(
            week_day=weekday, start_time=starttime, end_time=endtime)
        assert len(
            user.availability) == 1 and timeslot1dict in user.get_availability_timeslots()

        weekday2 = 'Tuesday'
        starttime2 = time(14, 0, 0)
        endtime2 = time(16, 0, 0)

        # Add second availability timeslot
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday2,
                              starttime=starttime2.strftime('%H:%M'),
                              endtime=endtime2.strftime('%H:%M')))
        user = M.User.query.get(username='test-admin')
        timeslot2dict = dict(week_day=weekday2,
                             start_time=starttime2, end_time=endtime2)
        assert len(user.availability) == 2 and timeslot1dict in user.get_availability_timeslots() \
            and timeslot2dict in user.get_availability_timeslots()

        # Remove availability timeslot
        r = self.app.post('/auth/user_info/availability/remove_timeslot',
                          params=dict(
                              weekday=weekday,
                              starttime=starttime.strftime('%H:%M'),
                              endtime=endtime.strftime('%H:%M')))
        user = M.User.query.get(username='test-admin')
        assert len(
            user.availability) == 1 and timeslot2dict in user.get_availability_timeslots()

        # Add invalid availability timeslot
        r = self.app.post('/auth/user_info/availability/add_timeslot',
                          params=dict(
                              weekday=weekday2,
                              starttime=endtime2.strftime('%H:%M'),
                              endtime=starttime2.strftime('%H:%M')))
        assert 'Invalid period:' in str(r)
        user = M.User.query.get(username='test-admin')
        timeslot2dict = dict(week_day=weekday2,
                             start_time=starttime2, end_time=endtime2)
        assert len(
            user.availability) == 1 and timeslot2dict in user.get_availability_timeslots()

    @td.with_user_project('test-admin')
    def test_inactivity(self):
        # Add inactivity period
        now = datetime.utcnow().date()
        now = datetime(now.year, now.month, now.day)
        startdate = now + timedelta(days=1)
        enddate = now + timedelta(days=7)
        self.app.get('/auth/user_info/availability/')
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate=startdate.strftime('%d/%m/%Y'),
                              enddate=enddate.strftime('%d/%m/%Y')))
        user = M.User.query.get(username='test-admin')
        period1dict = dict(start_date=startdate, end_date=enddate)
        assert len(
            user.inactiveperiod) == 1 and period1dict in user.get_inactive_periods()

        # Add second inactivity period
        startdate2 = now + timedelta(days=24)
        enddate2 = now + timedelta(days=28)
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate=startdate2.strftime('%d/%m/%Y'),
                              enddate=enddate2.strftime('%d/%m/%Y')))
        user = M.User.query.get(username='test-admin')
        period2dict = dict(start_date=startdate2, end_date=enddate2)
        assert len(user.inactiveperiod) == 2 and period1dict in user.get_inactive_periods() \
            and period2dict in user.get_inactive_periods()

        # Remove first inactivity period
        r = self.app.post(
            '/auth/user_info/availability/remove_inactive_period',
            params=dict(
                startdate=startdate.strftime('%d/%m/%Y'),
                enddate=enddate.strftime('%d/%m/%Y')))
        user = M.User.query.get(username='test-admin')
        assert len(
            user.inactiveperiod) == 1 and period2dict in user.get_inactive_periods()

        # Add invalid inactivity period
        r = self.app.post('/auth/user_info/availability/add_inactive_period',
                          params=dict(
                              startdate='NOT/A/DATE',
                              enddate=enddate2.strftime('%d/%m/%Y')))
        user = M.User.query.get(username='test-admin')
        assert 'Please enter a valid date' in str(r)
        assert len(
            user.inactiveperiod) == 1 and period2dict in user.get_inactive_periods()

    @td.with_user_project('test-admin')
    def test_skills(self):
        # Add a skill
        skill_cat = M.TroveCategory.query.get(show_as_skill=True)
        level = 'low'
        comment = 'test comment'
        result = self.app.get('/auth/user_info/skills/')
        r = self.app.post('/auth/user_info/skills/save_skill',
                          params=dict(
                              level=level,
                              comment=comment,
                              selected_skill=str(skill_cat.trove_cat_id)))
        user = M.User.query.get(username='test-admin')
        skilldict = dict(category_id=skill_cat._id,
                         comment=comment, level=level)
        assert len(user.skills) == 1 and skilldict in user.skills

        # Add again the same skill
        level = 'medium'
        comment = 'test comment 2'
        result = self.app.get('/auth/user_info/skills/')
        r = self.app.post('/auth/user_info/skills/save_skill',
                          params=dict(
                              level=level,
                              comment=comment,
                              selected_skill=str(skill_cat.trove_cat_id)))
        user = M.User.query.get(username='test-admin')
        skilldict = dict(category_id=skill_cat._id,
                         comment=comment, level=level)
        assert len(user.skills) == 1 and skilldict in user.skills

        # Add an invalid skill
        level2 = 'not a level'
        comment2 = 'test comment 2'
        r = self.app.post('/auth/user_info/skills/save_skill',
                          params=dict(
                              level=level2,
                              comment=comment2,
                              selected_skill=str(skill_cat.trove_cat_id)))
        user = M.User.query.get(username='test-admin')
        # Check that everything is as it was before
        assert len(user.skills) == 1 and skilldict in user.skills

        # Remove a skill
        self.app.get('/auth/user_info/skills/')
        self.app.post('/auth/user_info/skills/remove_skill',
                          params=dict(
                              categoryid=str(skill_cat.trove_cat_id)))
        user = M.User.query.get(username='test-admin')
        assert len(user.skills) == 0

    @td.with_user_project('test-admin')
    def test_user_message(self):
        assert not M.User.query.get(
            username='test-admin').get_pref('disable_user_messages')
        self.app.post('/auth/preferences/user_message')
        assert M.User.query.get(
            username='test-admin').get_pref('disable_user_messages')
        self.app.post('/auth/preferences/user_message',
                      params={'allow_user_messages': 'on'})
        assert not M.User.query.get(
            username='test-admin').get_pref('disable_user_messages')


class TestPasswordReset(TestController):

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_email_unconfirmed(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.query.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = False
        ThreadLocalORMSession.flush_all()
        self.app.post('/auth/password_recovery_hash', {'email': email._id})
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_user_disabled(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.query.find(
            {'claimed_by_user_id': user._id}).first()
        user.disabled = True
        ThreadLocalORMSession.flush_all()
        self.app.post('/auth/password_recovery_hash', {'email': email._id})
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        assert hash is None

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_password_reset(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.query.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        old_pw_hash = user.password
        r = self.app.post('/auth/password_recovery_hash', {'email': email._id})
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert hash is not None
        assert hash_expiry is not None

        r = self.app.get('/auth/forgotten_password/%s' % hash)
        assert_in('New Password:', r)
        assert_in('New Password (again):', r)
        form = r.forms[0]
        form['pw'] = form['pw2'] = new_password = '154321'
        r = form.submit()
        user = M.User.query.get(username='test-admin')
        assert_not_equal(old_pw_hash, user.password)
        provider = plugin.LocalAuthenticationProvider(None)
        assert_true(provider._validate_password(user, new_password))

        text = '''
To reset your password on %s, please visit the following URL:

%s/auth/forgotten_password/%s

''' % (config['site_name'], config['base_url'], hash)

        sendmail.post.assert_called_once_with(
            destinations=[email._id],
            fromaddr=config['forgemail.return_path'],
            reply_to=config['forgemail.return_path'],
            subject='Password recovery',
            message_id=gen_message_id(),
            text=text)
        user = M.User.query.get(username='test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        hash_expiry = user.get_tool_data('AuthPasswordReset', 'hash_expiry')
        assert_equal(hash, '')
        assert_equal(hash_expiry, '')

    @patch('allura.tasks.mail_tasks.sendmail')
    @patch('allura.lib.helpers.gen_message_id')
    def test_hash_expired(self, gen_message_id, sendmail):
        user = M.User.query.get(username='test-admin')
        email = M.EmailAddress.query.find(
            {'claimed_by_user_id': user._id}).first()
        email.confirmed = True
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/auth/password_recovery_hash', {'email': email._id})
        user = M.User.by_username('test-admin')
        hash = user.get_tool_data('AuthPasswordReset', 'hash')
        user.set_tool_data('AuthPasswordReset',
                           hash_expiry=datetime(2000, 10, 10))
        r = self.app.get('/auth/forgotten_password/%s' % hash.encode('utf-8'))
        assert_in('Unable to process reset, please try again', r.follow().body)
        r = self.app.post('/auth/set_new_password/%s' %
                          hash.encode('utf-8'), {'pw': '154321', 'pw2': '154321'})
        assert_in('Unable to process reset, please try again', r.follow().body)

    @patch('allura.lib.plugin.AuthenticationProvider')
    def test_provider_disabled(self, AP):
        user = M.User.query.get(username='test-admin')
        ap = AP.get()
        ap.forgotten_password_process = False
        ap.authenticate_request()._id = user._id
        self.app.get('/auth/forgotten_password', status=404)
        self.app.post('/auth/set_new_password',
                      {'pw': 'foo', 'pw2': 'foo'}, status=404)
        self.app.post('/auth/password_recovery_hash',
                      {'email': 'foo'}, status=404)


class TestOAuth(TestController):

    def test_register_deregister_app(self):
        # register
        r = self.app.get('/auth/oauth/')
        r = self.app.post('/auth/oauth/register',
                          params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez'}).follow()
        assert 'oautstapp' in r
        # deregister
        assert_equal(r.forms[0].action, 'deregister')
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert 'oautstapp' not in r

    def test_generate_revoke_access_token(self):
        # generate
        r = self.app.post('/auth/oauth/register',
                          params={'application_name': 'oautstapp', 'application_description': 'Oauth rulez'}).follow()
        assert_equal(r.forms[1].action, 'generate_access_token')
        r.forms[1].submit()
        r = self.app.get('/auth/oauth/')
        assert 'Bearer Token:' in r
        assert_not_equal(
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')), [])
        # revoke
        assert_equal(r.forms[0].action, 'revoke_access_token')
        r.forms[0].submit()
        r = self.app.get('/auth/oauth/')
        assert_not_equal(r.forms[0].action, 'revoke_access_token')
        assert_equal(
            M.OAuthAccessToken.for_user(M.User.by_username('test-admin')), [])

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_interactive(self, Request, Server):
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-admin')
        consumer_token = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_callback': 'http://my.domain.com/callback',
        }
        r = self.app.post('/rest/oauth/request_token', params={})
        rtok = parse_qs(r.body)['oauth_token'][0]
        r = self.app.post('/rest/oauth/authorize',
                          params={'oauth_token': rtok})
        r = r.forms[0].submit('yes')
        assert r.location.startswith('http://my.domain.com/callback')
        pin = parse_qs(urlparse(r.location).query)['oauth_verifier'][0]
        #pin = r.html.find(text=re.compile('^PIN: ')).split()[1]
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': rtok,
            'oauth_verifier': pin,
        }
        r = self.app.get('/rest/oauth/access_token')
        atok = parse_qs(r.body)
        assert_equal(len(atok['oauth_token']), 1)
        assert_equal(len(atok['oauth_token_secret']), 1)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_valid(self, Request, Server):
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-user')
        consumer_token = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key'}
        r = self.app.post('/rest/oauth/request_token', params={'key': 'value'})
        Request.from_request.assert_called_once_with(
            'POST', 'http://localhost/rest/oauth/request_token',
            headers={'Host': 'localhost:80', 'Content-Type':
                    'application/x-www-form-urlencoded; charset="utf-8"'},
            parameters={'key': 'value'},
            query_string='')
        Server().verify_request.assert_called_once_with(
            req, consumer_token.consumer, None)
        request_token = M.OAuthRequestToken.query.get(
            consumer_token_id=consumer_token._id)
        assert_is_not_none(request_token)
        assert_equal(r.body, request_token.to_string())

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_no_consumer_token(self, Request, Server):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key'}
        r = self.app.post('/rest/oauth/request_token',
                          params={'key': 'value'}, status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_request_token_invalid(self, Request, Server):
        Server().verify_request.side_effect = ValueError
        M.OAuthConsumerToken.consumer = mock.Mock()
        user = M.User.by_username('test-user')
        consumer_token = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key'}
        self.app.post('/rest/oauth/request_token',
                          params={'key': 'value'}, status=403)

    def test_authorize_ok(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/authorize',
                          params={'oauth_token': 'api_key'})
        assert_in('ctok_desc', r.body)
        assert_in('api_key', r.body)

    def test_authorize_invalid(self):
        self.app.post('/rest/oauth/authorize',
                          params={'oauth_token': 'api_key'}, status=403)

    def test_do_authorize_no(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        self.app.post('/rest/oauth/do_authorize',
                          params={'no': '1', 'oauth_token': 'api_key'})
        assert_is_none(M.OAuthRequestToken.query.get(api_key='api_key'))

    def test_do_authorize_oob(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='oob',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize',
                          params={'yes': '1', 'oauth_token': 'api_key'})
        assert_is_not_none(r.html.find(text=re.compile('^PIN: ')))

    def test_do_authorize_cb(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize',
                          params={'yes': '1', 'oauth_token': 'api_key'})
        assert r.location.startswith(
            'http://my.domain.com/callback?oauth_token=api_key&oauth_verifier=')

    def test_do_authorize_cb_params(self):
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.post('/rest/oauth/do_authorize',
                          params={'yes': '1', 'oauth_token': 'api_key'})
        assert r.location.startswith(
            'http://my.domain.com/callback?myparam=foo&oauth_token=api_key&oauth_verifier=')

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_no_consumer(self, Request):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_no_request(self, Request):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_bad_pin(self, Request):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'bad',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_bad_sig(self, Request, Server):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        Server().verify_request.side_effect = ValueError
        self.app.get('/rest/oauth/access_token', status=403)

    @mock.patch('allura.controllers.rest.oauth.Server')
    @mock.patch('allura.controllers.rest.oauth.Request')
    def test_access_token_ok(self, Request, Server):
        req = Request.from_request.return_value = {
            'oauth_consumer_key': 'api_key',
            'oauth_token': 'api_key',
            'oauth_verifier': 'good',
        }
        user = M.User.by_username('test-admin')
        ctok = M.OAuthConsumerToken(
            api_key='api_key',
            user_id=user._id,
            description='ctok_desc',
        )
        rtok = M.OAuthRequestToken(
            api_key='api_key',
            consumer_token_id=ctok._id,
            callback='http://my.domain.com/callback?myparam=foo',
            user_id=user._id,
            validation_pin='good',
        )
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/rest/oauth/access_token')
        atok = parse_qs(r.body)
        assert_equal(len(atok['oauth_token']), 1)
        assert_equal(len(atok['oauth_token_secret']), 1)
