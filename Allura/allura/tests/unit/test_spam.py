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
            HTTP_X_REMOTE_ADDR='some ip',
            HTTP_USER_AGENT='some browser',
            HTTP_REFERER='some url')
        self.content = 'spam text'
        self.expected_data = dict(
            comment_content=self.content,
            comment_type='comment',
            user_ip='some ip',
            user_agent='some browser',
            referrer='some url')

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check(self.content)
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_explicit_content_type(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check(self.content, content_type='some content type')
        self.expected_data['comment_type'] = 'some content type'
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=self.expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_artifact(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check(self.content, artifact=self.fake_artifact)
        expected_data = self.expected_data
        expected_data['permalink'] = 'artifact url'
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_user(self, request, c):
        request.environ = self.fake_environ
        c.user = None
        self.akismet.check(self.content, user=self.fake_user)
        expected_data = self.expected_data
        expected_data.update(comment_author='Some User',
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)

    @mock.patch('allura.lib.spam.akismetservice.c')
    @mock.patch('allura.lib.spam.akismetservice.request')
    def test_check_with_implicit_user(self, request, c):
        request.environ = self.fake_environ
        c.user = self.fake_user
        self.akismet.check(self.content)
        expected_data = self.expected_data
        expected_data.update(comment_author='Some User',
                comment_author_email='user@domain')
        self.akismet.comment_check.assert_called_once_with(self.content,
                data=expected_data, build_data=False)
