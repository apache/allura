import re


class GitHubMarkdownConverter(object):

    @classmethod
    def convert(cls, text):
        _re = re.compile('\S*(#\d+)')
        text = _re.sub(cls._convert_ticket, text)

        _re = re.compile('\S*/\S*@(\w{40})')
        text = _re.sub(cls._convert_user_repo_sha, text)

        _re = re.compile('\s\S*@(\w{40})')
        text = _re.sub(cls._convert_user_sha, text)

        _re = re.compile(': (\w{40})')
        text = _re.sub(cls._convert_sha, text)
        _re = re.compile('~~(.*)~~',)
        text = _re.sub(cls._convert_strikethrough, text)
        _re = re.compile(r'```\w*(.*)```', re.DOTALL)
        text = _re.sub(cls._convert_codeblock, text)
        return text

    @classmethod
    def _convert_sha(cls, match):
        return ': [%s]' % match.group(1)[:6]

    @classmethod
    def _convert_ticket(cls, match):
        return '[%s]' % match.group(1)

    @classmethod
    def _convert_user_sha(cls, match):
        return '[%s]' % (match.group(1)[:6])

    @classmethod
    def _convert_user_repo_sha(cls, match):
        return '[%s]' % (match.group(1)[:6])

    @classmethod
    def _convert_strikethrough(cls, match):
        return '<s>%s</s>' % match.group(1)

    @classmethod
    def _convert_codeblock(cls, match):
        return '\n~~~~%s~~~~\n'% match.group(1)
