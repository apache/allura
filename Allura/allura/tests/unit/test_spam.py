# -*- coding: utf-8 -*-

import mock
import unittest
import urllib

try:
    from allura.lib.spam.akismetservice import Akismet
except ImportError:
    Akismet = None


@unittest.skipIf(Akismet is None, "Can't import Akismet")
class TestAkismet(unittest.TestCase):
    def setUp(self):
        self.akismet = Akismet()
        def side_effect(*args, **kw):
            # side effect to test that data being sent to
            # akismet can be successfully urlencoded
            urllib.urlencode(kw.get('data', {}))
        self.akismet.comment_check = mock.Mock(side_effect=side_effect)
        self.fake_artifact = mock.Mock(**{'url.return_value': 'artifact url'})
        self.fake_user = mock.Mock(display_name=u'Søme User',
                email_addresses=['user@domain'])
        self.fake_headers = dict(
            REMOTE_ADDR='fallback ip',
            X_FORWARDED_FOR='some ip',
            USER_AGENT='some browser',
            REFERER='some url')
        self.content = u'spåm text'
        self.expected_data = dict(
            comment_content=self.content.encode('utf8'),
            comment_type='comment',
            user_ip='some ip',
            user_agent='some browser',
            referrer='some url')

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check(self, request, c):
        request.headers = self.fake_headers
        c.user = None
        self.akismet.check(self.content)
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_explicit_content_type(self, request, c):
        request.headers = self.fake_headers
        c.user = None
        self.akismet.check(self.content, content_type='some content type')
        self.expected_data['comment_type'] = 'some content type'
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_artifact(self, request, c):
        request.headers = self.fake_headers
        c.user = None
        self.akismet.check(self.content, artifact=self.fake_artifact)
        expected_data = self.expected_data
        expected_data['permalink'] = 'artifact url'
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_user(self, request, c):
        request.headers = self.fake_headers
        c.user = None
        self.akismet.check(self.content, user=self.fake_user)
        expected_data = self.expected_data
        expected_data.update(comment_author=u'Søme User'.encode('utf8'),
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_implicit_user(self, request, c):
        request.headers = self.fake_headers
        c.user = self.fake_user
        self.akismet.check(self.content)
        expected_data = self.expected_data
        expected_data.update(comment_author=u'Søme User'.encode('utf8'),
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_fallback_ip(self, request, c):
        self.expected_data['user_ip'] = 'fallback ip'
        self.fake_headers.pop('X_FORWARDED_FOR')
        request.headers = self.fake_headers
        request.remote_addr = self.fake_headers['REMOTE_ADDR']
        c.user = None
        self.akismet.check(self.content)
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=self.expected_data, build_data=False)
