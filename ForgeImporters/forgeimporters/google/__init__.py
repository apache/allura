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

import re
import urllib
from urlparse import urlparse, urljoin, parse_qs
from collections import defaultdict
from contextlib import closing
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import logging

from BeautifulSoup import BeautifulSoup

from allura.lib import helpers as h
from allura import model as M
from forgeimporters.base import ProjectExtractor


log = logging.getLogger(__name__)

def _as_text(node, chunks=None):
    """
    Similar to node.text, but preserves whitespace around tags,
    and converts <br/>s to \n.
    """
    if chunks is None:
        chunks = []
    for n in node:
        if isinstance(n, basestring):
            chunks.append(n)
        elif n.name == 'br':
            chunks.append('\n')
        else:
            _as_text(n, chunks)
    return ''.join(chunks)


class GoogleCodeProjectExtractor(ProjectExtractor):
    BASE_URL = 'http://code.google.com'
    RE_REPO_TYPE = re.compile(r'(svn|hg|git)')

    PAGE_MAP = {
            'project_info': BASE_URL + '/p/{project_name}/',
            'source_browse': BASE_URL + '/p/{project_name}/source/browse/',
            'issues_csv': BASE_URL + '/p/{project_name}/issues/csv?can=1&colspec=ID&start={start}',
            'issue': BASE_URL + '/p/{project_name}/issues/detail?id={issue_id}',
        }

    LICENSE_MAP = defaultdict(lambda:'Other/Proprietary License', {
            'Apache License 2.0': 'Apache Software License',
            'Artistic License/GPL': 'Artistic License',
            'Eclipse Public License 1.0': 'Eclipse Public License',
            'GNU GPL v2': 'GNU General Public License (GPL)',
            'GNU GPL v3': 'GNU General Public License (GPL)',
            'GNU Lesser GPL': 'GNU Library or Lesser General Public License (LGPL)',
            'MIT License': 'MIT License',
            'Mozilla Public License 1.1': 'Mozilla Public License 1.1 (MPL 1.1)',
            'New BSD License': 'BSD License',
            'Other Open Source': 'Other/Proprietary License',
        })

    DEFAULT_ICON = 'http://www.gstatic.com/codesite/ph/images/defaultlogo.png'

    def get_short_description(self, project):
        page = self.get_page('project_info')
        project.short_description = page.find(itemprop='description').string.strip()

    def get_icon(self, project):
        page = self.get_page('project_info')
        icon_url = urljoin(self.url, page.find(itemprop='image').get('src'))
        if icon_url == self.DEFAULT_ICON:
            return
        icon_name = urllib.unquote(urlparse(icon_url).path).split('/')[-1]
        fp_ish = self.urlopen(icon_url)
        fp = StringIO(fp_ish.read())
        M.ProjectFile.save_image(
            icon_name, fp,
            fp_ish.info()['content-type'].split(';')[0],  # strip off charset=x extra param,
            square=True, thumbnail_size=(48,48),
            thumbnail_meta={'project_id': project._id, 'category': 'icon'})

    def get_license(self, project):
        page = self.get_page('project_info')
        license = page.find(text='Code license').findNext().find('a').string.strip()
        trove = M.TroveCategory.query.get(fullname=self.LICENSE_MAP[license])
        project.trove_license.append(trove._id)

    def get_repo_type(self):
        page = self.get_page('source_browse')
        repo_type = page.find(id="crumb_root")
        if not repo_type:
            raise Exception("Couldn't detect repo type: no #crumb_root in "
                    "{0}".format(self.url))
        re_match = self.RE_REPO_TYPE.match(repo_type.text.lower())
        if re_match:
            return re_match.group(0)
        else:
            raise Exception("Unknown repo type: {0}".format(repo_type.text))

    @classmethod
    def _get_issue_ids_page(cls, project_name, start):
        url = cls.PAGE_MAP['issues_csv'].format(project_name=project_name, start=start)
        with closing(cls.urlopen(url)) as fp:
            lines = fp.readlines()[1:]  # skip CSV header
            if not lines[-1].startswith('"'):
                lines.pop()  # skip "next page here" info footer
        issue_ids = [line.strip('",\n') for line in lines]
        return issue_ids

    @classmethod
    def iter_issues(cls, project_name):
        """
        Iterate over all issues for a project,
        using paging to keep the responses reasonable.
        """
        start = 0
        limit = 100

        while True:
            issue_ids = cls._get_issue_ids_page(project_name, start)
            if len(issue_ids) <= 0:
                return
            for issue_id in issue_ids:
                yield (int(issue_id), cls(project_name, 'issue', issue_id=issue_id))
            start += limit

    def get_issue_summary(self):
        text = self.page.find(id='issueheader').findAll('td', limit=2)[1].span.string.strip()
        bs = BeautifulSoup(text, convertEntities=BeautifulSoup.HTML_ENTITIES)
        return bs.string

    def get_issue_description(self):
        return _as_text(self.page.find(id='hc0').pre).strip()

    def get_issue_created_date(self):
        return self.page.find(id='hc0').find('span', 'date').get('title')

    def get_issue_mod_date(self):
        comments = self.page.findAll('div', 'issuecomment')
        if comments:
            last_update = Comment(comments[-1])
            return last_update.created_date
        else:
            return self.get_issue_created_date()

    def get_issue_creator(self):
        a = self.page.find(id='hc0').find(True, 'userlink')
        return UserLink(a)

    def get_issue_status(self):
        tag = self.page.find(id='issuemeta').find('th', text=re.compile('Status:')).findNext().span
        if tag:
            return tag.string.strip()
        else:
            return ''

    def get_issue_owner(self):
        tag = self.page.find(id='issuemeta').find('th', text=re.compile('Owner:')).findNext().find(True, 'userlink')
        if tag:
            return UserLink(tag)
        else:
            return None

    def get_issue_labels(self):
        label_nodes = self.page.find(id='issuemeta').findAll('a', 'label')
        return [_as_text(l) for l in label_nodes]

    def get_issue_attachments(self):
        attachments = self.page.find(id='hc0').find('div', 'attachments')
        if attachments:
            return [Attachment(a.parent) for a in attachments.findAll('a', text='Download')]
        else:
            return []

    def get_issue_stars(self):
        stars_re = re.compile(r'(\d+) (person|people) starred this issue')
        stars = self.page.find(id='issueheader').find(text=stars_re)
        if stars:
            return int(stars_re.search(stars).group(1))
        return 0

    def iter_comments(self):
        for comment in self.page.findAll('div', 'issuecomment'):
            yield Comment(comment)

class UserLink(object):
    def __init__(self, tag):
        self.name = tag.string.strip()
        if tag.get('href'):
            self.url = urljoin(GoogleCodeProjectExtractor.BASE_URL, tag.get('href'))
        else:
            self.url = None

    def __str__(self):
        if self.url:
            return '[{name}]({url})'.format(name = self.name, url = self.url)
        else:
            return self.name

class Comment(object):
    def __init__(self, tag):
        self.author = UserLink(tag.find('span', 'author').find(True, 'userlink'))
        self.created_date = tag.find('span', 'date').get('title')
        self.body = _as_text(tag.find('pre')).strip()
        self._get_updates(tag)
        self._get_attachments(tag)

    def _get_updates(self, tag):
        _updates = tag.find('div', 'updates')
        if _updates:
            _strings = _updates.findAll(text=True)
            updates = (s.strip() for s in _strings if s.strip())
            self.updates = {field: updates.next() for field in updates}
        else:
            self.updates = {}

    def _get_attachments(self, tag):
        attachments = tag.find('div', 'attachments')
        if attachments:
            self.attachments = [Attachment(a.parent) for a in attachments.findAll('a', text='Download')]
        else:
            self.attachments = []

    @property
    def annotated_text(self):
        text = (
                u'*Originally posted by:* {author}\n'
                u'\n'
                u'{body}\n'
                u'\n'
                u'{updates}'
            ).format(
                author=self.author,
                body=h.plain2markdown(self.body, preserve_multiple_spaces=True, has_html_entities=True),
                updates='\n'.join(
                        '**%s** %s' % (k,v)
                        for k,v in self.updates.items()
                    ),
            )
        return text

class Attachment(object):
    def __init__(self, tag):
        self.url = urljoin(GoogleCodeProjectExtractor.BASE_URL, tag.get('href'))
        self.filename = parse_qs(urlparse(self.url).query)['name'][0]
        self.type = None

    @property
    def file(self):
        fp_ish = GoogleCodeProjectExtractor(None).urlopen(self.url)
        fp = StringIO(fp_ish.read())
        return fp
