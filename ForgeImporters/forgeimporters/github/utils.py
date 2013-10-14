import re


class GitHubMarkdownConverter(object):

    def __init__(self, gh_user, gh_project, project, mount_point):
        self.gh_project = '%s/%s' % (gh_project, gh_user)
        self.project = '%s:%s' % (project, mount_point)

    def convert(self, text):
        _re = re.compile('\S+\s+(#\d+)')
        text = _re.sub(self._convert_ticket, text)

        _re = re.compile('\S*/\S*@([0-9a-f]{40})')
        text = _re.sub(self._convert_user_repo_sha, text)

        _re = re.compile('\s\S*@([0-9a-f]{40})')
        text = _re.sub(self._convert_user_sha, text)

        _re = re.compile('(\s|^)([0-9a-f]{40})(\s|$)')
        text = _re.sub(self._convert_sha, text)

        _re = re.compile('~~(.*)~~',)
        text = _re.sub(self._convert_strikethrough, text)

        _re = re.compile(r'```\w*(.*)```', re.DOTALL)
        text = _re.sub(self._convert_codeblock, text)
        return text

    def _convert_sha(self, match):
        return '%s[%s]%s' % (match.group(1), match.group(2)[:6], match.group(3))

    def _convert_ticket(self, match):
        return '[%s]' % match.group(1)

    def _convert_user_sha(self, match):
        return '[%s]' % (match.group(1)[:6])

    def _convert_user_repo_sha(self, match):
        return '[%s]' % (match.group(1)[:6])

    def _convert_strikethrough(self, match):
        return '<s>%s</s>' % match.group(1)

    def _convert_codeblock(self, match):
        return '~~~~%s~~~~'% match.group(1)
