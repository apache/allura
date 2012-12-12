import mock
import unittest

try:
    from allura.lib.spam.akismetservice import Akismet
except ImportError:
    Akismet = None


@unittest.skipIf(Akismet is None, "Can't import Akismet")
class TestAkismet(unittest.TestCase):
    def setUp(self):
        self.akismet = Akismet()
        self.akismet.comment_check = mock.Mock()
        self.fake_artifact = mock.Mock(**{'url.return_value': 'artifact url'})
        self.fake_user = mock.Mock(display_name='Some User',
                email_addresses=['user@domain'])
        self.fake_environ = dict(
            REMOTE_ADDR='some ip',
            HTTP_USER_AGENT='some browser',
            HTTP_REFERER='some url')
        self.expected_data = dict(
            comment_type='comment',
            user_ip='some ip',
            user_agent='some browser',
            referrer='some url')

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check('spam text')
        self.akismet.comment_check.assert_called_once_with('spam text',
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_explicit_content_type(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check('spam text', content_type='some content type')
        self.expected_data['comment_type'] = 'some content type'
        self.akismet.comment_check.assert_called_once_with('spam text',
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_artifact(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check('spam text', artifact=self.fake_artifact)
        expected_data = self.expected_data
        expected_data['permalink'] = 'artifact url'
        self.akismet.comment_check.assert_called_once_with('spam text',
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_user(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check('spam text', user=self.fake_user)
        expected_data = self.expected_data
        expected_data.update(comment_author='Some User',
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with('spam text',
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_implicit_user(self, request, c):
        request.environ = self.fake_environ
        c.user = self.fake_user
        self.akismet.check('spam text')
        expected_data = self.expected_data
        expected_data.update(comment_author='Some User',
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with('spam text',
                data=expected_data, build_data=False)
