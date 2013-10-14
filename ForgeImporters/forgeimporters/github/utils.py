import re


class GitHubMarkdownConverter(object):

    def __init__(self, gh_user, gh_project, project, mount_point):
        self.gh_project = '%s/%s' % (gh_user, gh_project)
        self.project = '%s:%s' % (project, mount_point)
        self.gh_base_url = u'https://github.com/'

    def convert(self, text):
        _re = re.compile(r'(\s|^)(\S+)/(\S+)#(\d+)(\s|$)')
        text = _re.sub(self._convert_user_repo_ticket, text)

        _re = re.compile(r'(\s|^)(\S+)#(\d+)(\s|$)')
        text = _re.sub(self._convert_user_ticket, text)

        _re = re.compile(r'(\S+\s+)(#\d+)')
        text = _re.sub(self._convert_ticket, text)

        _re = re.compile(r'(\s|^)(\S+)/(\S+)@([0-9a-f]{40})(\s|$)')
        text = _re.sub(self._convert_user_repo_sha, text)

        _re = re.compile(r'(\s|^)(\S+)@([0-9a-f]{40})(\s|$)')
        text = _re.sub(self._convert_user_sha, text)

        _re = re.compile(r'(\s|^)([0-9a-f]{40})(\s|$)')
        text = _re.sub(self._convert_sha, text)

        _re = re.compile(r'~~(.*)~~',)
        text = _re.sub(self._convert_strikethrough, text)

        _re = re.compile(r'```\w*(.*)```', re.DOTALL)
        text = _re.sub(self._convert_codeblock, text)
        return text

    def _gh_commit_url(self, project, sha, title):
        return u'[%s](%s)' % (title, self.gh_base_url + project + '/commit/' + sha)

    def _gh_ticket_url(self, project, tid, title):
        return u'[%s](%s)' % (title, self.gh_base_url + project + '/issues/' + str(tid))

    def _convert_sha(self, m):
        return '%s[%s]%s' % (m.group(1), m.group(2)[:6], m.group(3))

    def _convert_ticket(self, m):
        return '%s[%s]' % m.groups()

    def _convert_user_ticket(self, m):
        user = m.group(2)
        tid = m.group(3)
        if self.gh_project.startswith(user + '/'):
            return '%s[%s]%s' % (m.group(1), '#' + tid, m.group(4))
        return m.group(0)

    def _convert_user_repo_ticket(self, m):
        project = '%s/%s' % (m.group(2), m.group(3))
        tid = m.group(4)
        if project == self.gh_project:
            link = ':'.join([self.project, '#' + tid])
            return '%s[%s]%s' % (m.group(1), link, m.group(5))
        title = project + '#' + tid
        return ''.join([m.group(1),
                        self._gh_ticket_url(project, tid, title),
                        m.group(5)])

    def _convert_user_sha(self, m):
        user = m.group(2)
        sha = m.group(3)
        if self.gh_project.startswith(user + '/'):
            return '%s[%s]%s' % (m.group(1), sha[:6], m.group(4))
        return m.group(0)

    def _convert_user_repo_sha(self, m):
        project = '%s/%s' % (m.group(2), m.group(3))
        sha = m.group(4)
        if project == self.gh_project:
            link = ':'.join([self.project, sha[:6]])
            return '%s[%s]%s' % (m.group(1), link, m.group(5))
        title = project + '@' + sha[:6]
        return ''.join([m.group(1),
                        self._gh_commit_url(project, sha, title),
                        m.group(5)])

    def _convert_strikethrough(self, m):
        return '<s>%s</s>' % m.group(1)

    def _convert_codeblock(self, m):
        return '~~~~%s~~~~'% m.group(1)
