from nose.tools import assert_equal

from forgeimporters.github.utils import GitHubMarkdownConverter


class TestGitHubMarkdownConverter(object):

    def setUp(self):
        self.conv = GitHubMarkdownConverter

    def test_convert_sha_github_markup(self):
        text = 'SHA: 16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, 'SHA: [16c999]')

    def test_convert_user_sha_github_markup(self):
        text = 'User@SHA: mojombo@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, 'User@SHA:[16c999]')

    def test_convert_user_repo_sha_github_markup(self):
        text = 'User/Repository@SHA: mojombo/github-flavored-markdown@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, 'User/Repository@SHA: [16c999]')

    def test_convert_ticket_github_markup(self):
        text = 'Ticket: #1'
        result = self.conv.convert(text)
        assert_equal(result, 'Ticket: [#1]')

    def test_convert_username_ticket_github_markup(self):
        text = 'User#Num: user#1'
        result = self.conv.convert(text)
        assert_equal(result, 'User#Num: [#1]')

    def test_convert_username_repo_ticket_github_markup(self):
        text = 'User/Repository#Num: user/repo#1'
        result = self.conv.convert(text)
        assert_equal(result, 'User/Repository#Num: [#1]')
