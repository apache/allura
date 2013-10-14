from nose.tools import assert_equal

from forgeimporters.github.utils import GitHubMarkdownConverter


class TestGitHubMarkdownConverter(object):

    def setUp(self):
        self.conv = GitHubMarkdownConverter('user', 'project', 'p', 'mount')

    def test_convert_sha(self):
        text = '16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, '[16c999]')

        text = 'some context  16c999e8c71134401a78d4d46435517b2271d6ac '
        result = self.conv.convert(text)
        assert_equal(result, 'some context  [16c999] ')

    def test_convert_user_sha(self):
        text = 'user@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, '[16c999]')

        # Not an owner of current project
        text = 'another-user@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, text)

    def test_convert_user_repo_sha(self):
        text = 'user/project@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, '[p:mount:16c999]')

        # Not a current project
        text = 'user/p@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert_equal(result, '[user/p@16c999]'
                             '(https://github.com/user/p/commit/16c999e8c71134401a78d4d46435517b2271d6ac)')

    def test_convert_ticket(self):
        text = 'Ticket #1'
        result = self.conv.convert(text)
        assert_equal(result, 'Ticket [#1]')

        # github treats '#' in the begining as a header
        text = '#1'
        assert_equal(self.conv.convert(text), '#1')
        text = '  #1'
        assert_equal(self.conv.convert(text), '  #1')

    def test_convert_user_ticket(self):
        text = 'user#1'
        result = self.conv.convert(text)
        assert_equal(result, '[#1]')

        # Not an owner of current project
        text = 'another-user#1'
        result = self.conv.convert(text)
        assert_equal(result, 'another-user#1')

    def test_convert_user_repo_ticket(self):
        text = 'user/project#1'
        result = self.conv.convert(text)
        assert_equal(result, '[p:mount:#1]')

        # Not a current project
        text = 'user/p#1'
        result = self.conv.convert(text)
        assert_equal(result, '[user/p#1](https://github.com/user/p/issues/1)')

    def test_convert_strikethrough(self):
        text = '~~mistake~~'
        assert_equal(self.conv.convert(text), '<s>mistake</s>')

    def test_convert_code_blocks(self):
        text = u'''```python
print "Hello!"
```'''
        result = u'~~~~\nprint "Hello!"\n~~~~'
        assert_equal(self.conv.convert(text).strip(), result)
