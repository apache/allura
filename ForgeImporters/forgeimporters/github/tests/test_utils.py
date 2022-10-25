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

from forgeimporters.github.utils import GitHubMarkdownConverter


class TestGitHubMarkdownConverter:

    def setup_method(self, method):
        self.conv = GitHubMarkdownConverter('user', 'project')

    def test_convert_sha(self):
        text = '16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert result == '[16c999]'

        text = 'some context  16c999e8c71134401a78d4d46435517b2271d6ac '
        result = self.conv.convert(text)
        assert result == 'some context  [16c999] '

    def test_convert_user_sha(self):
        text = 'user@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert result == '[16c999]'

        # Not an owner of current project
        text = 'another-user@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert result == text

    def test_convert_user_repo_sha(self):
        text = 'user/project@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert result == '[16c999]'

        # Not a current project
        text = 'user/p@16c999e8c71134401a78d4d46435517b2271d6ac'
        result = self.conv.convert(text)
        assert (result == '[user/p@16c999]'
                             '(https://github.com/user/p/commit/16c999e8c71134401a78d4d46435517b2271d6ac)')

    def test_convert_ticket(self):
        text = 'Ticket #1'
        result = self.conv.convert(text)
        assert result == 'Ticket [#1]'
        assert self.conv.convert('#1') == '[#1]'

    def test_convert_user_ticket(self):
        text = 'user#1'
        result = self.conv.convert(text)
        assert result == '[#1]'

        # Not an owner of current project
        text = 'another-user#1'
        result = self.conv.convert(text)
        assert result == 'another-user#1'

    def test_convert_user_repo_ticket(self):
        text = 'user/project#1'
        result = self.conv.convert(text)
        assert result == '[#1]'

        # Not a current project
        text = 'user/p#1'
        result = self.conv.convert(text)
        assert result == '[user/p#1](https://github.com/user/p/issues/1)'

    def test_convert_strikethrough(self):
        text = '~~mistake~~'
        assert self.conv.convert(text) == '<s>mistake</s>'

    def test_inline_code_block(self):
        text = 'This `~~some text~~` converts to this ~~strike out~~.'
        result = 'This `~~some text~~` converts to this <s>strike out</s>.'
        assert self.conv.convert(text).strip() == result

    def test_convert_code_blocks(self):
        text = '''```python
print "Hello!"
```

Two code blocks here!

```
for (var i = 0; i < a.length; i++) {
    console.log(i);
}
```'''
        result = ''':::python
    print "Hello!"

Two code blocks here!

    for (var i = 0; i < a.length; i++) {
        console.log(i);
    }'''

        assert self.conv.convert(text).strip() == result

    def test_code_blocks_without_newline_before(self):
        text = '''
There are some code snippet:
```
print 'Hello'
```
Pretty cool, ha?'''

        result = '''
There are some code snippet:

    print 'Hello'
Pretty cool, ha?'''
        assert self.conv.convert(text).strip() == result.strip()
        text = text.replace('```', '~~~')
        assert self.conv.convert(text).strip() == result.strip()

        text = '''
There are some code snippet:
```python
print 'Hello'
```
Pretty cool, ha?'''

        result = '''
There are some code snippet:

    :::python
    print 'Hello'
Pretty cool, ha?'''
        assert self.conv.convert(text).strip() == result.strip()
