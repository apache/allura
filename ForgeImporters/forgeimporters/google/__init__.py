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
from urllib2 import HTTPError
from urlparse import urlparse, urljoin, parse_qs
from collections import defaultdict
import logging
import os

import requests
from BeautifulSoup import BeautifulSoup
from formencode import validators as fev

from allura.lib import helpers as h
from allura import model as M
from forgeimporters.base import ProjectExtractor
from forgeimporters.base import File


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


def _as_markdown(tag, project_name):
    fragments = []
    for fragment in tag:
        if getattr(fragment, 'name', None) == 'a':
            href = urlparse(fragment['href'])
            qs = parse_qs(href.query)
            gc_link = not href.netloc or href.netloc == 'code.google.com'
            path_parts = href.path.split('/')
            target_project = None
            if gc_link:
                if len(path_parts) >= 5 and path_parts[1] == 'a':
                    target_project = '/'.join(path_parts[1:5])
                elif len(path_parts) >= 3:
                    target_project = path_parts[2]
            internal_link = target_project == project_name
            if gc_link and internal_link and 'id' in qs:
                # rewrite issue 123 project-internal issue links
                fragment = '[%s](#%s)' % (fragment.text, qs['id'][0])
            elif gc_link and internal_link and 'r' in qs:
                # rewrite r123 project-internal revision links
                fragment = '[r%s]' % qs['r'][0]
            elif gc_link:
                # preserve GC-internal links (probably issue PROJECT:123
                # inter-project issue links)
                fragment = '[%s](%s)' % (
                    h.plain2markdown(
                        fragment.text, preserve_multiple_spaces=True, has_html_entities=True),
                    # possibly need to adjust this URL for /a/ hosted domain URLs,
                    # but it seems fragment['href'] always starts with / so it replaces the given path
                    urljoin('https://code.google.com/p/%s/issues/' %
                            project_name, fragment['href']),
                )
            else:
                # convert all other links to Markdown syntax
                fragment = '[%s](%s)' % (fragment.text, fragment['href'])
        elif getattr(fragment, 'name', None) == 'i':
            # preserve styling of "(No comment was entered for this change.)"
            # messages
            fragment = '*%s*' % h.plain2markdown(fragment.text,
                                                 preserve_multiple_spaces=True, has_html_entities=True)
        elif getattr(fragment, 'name', None) == 'b':
            # preserve styling of issue template
            fragment = '**%s**' % h.plain2markdown(fragment.text,
                                                   preserve_multiple_spaces=True, has_html_entities=True)
        elif getattr(fragment, 'name', None) == 'br':
            # preserve forced line-breaks
            fragment = '\n'
        else:
            # convert all others to plain MD
            fragment = h.plain2markdown(
                unicode(fragment), preserve_multiple_spaces=True, has_html_entities=True)
        fragments.append(fragment)
    return ''.join(fragments).strip()


def csv_parser(page):
    lines = page.readlines()
    if not lines:
        return []
    # skip CSV header
    lines = lines[1:]
    # skip "next page here" info footer
    if not lines[-1].startswith('"'):
        lines.pop()
    # remove CSV wrapping (quotes, commas, newlines)
    return [line.strip('",\n') for line in lines]


class GoogleCodeProjectNameValidator(fev.FancyValidator):
    not_empty = True
    messages = {
        'invalid': 'Please enter a project URL, or a project name containing '
                   'only letters, numbers, and dashes.',
        'unavailable': 'This project is unavailable for import',
    }

    def _to_python(self, value, state=None):
        project_name_re = re.compile(r'^[a-z0-9][a-z0-9-]{,61}$')
        if project_name_re.match(value):
            # just a name
            project_name = value
        else:
            # try as a URL
            project_name = None
            project_name_simple = None
            url = urlparse(value.strip())
            if url.netloc.endswith('.googlecode.com'):
                project_name = url.netloc.split('.')[0]
            elif url.netloc == 'code.google.com':
                path_parts = url.path.lstrip('/').split('/')
                if len(path_parts) >= 2 and path_parts[0] == 'p':
                    project_name = path_parts[1]
                elif len(path_parts) >= 4 and path_parts[0] == 'a' and path_parts[2] == 'p':
                    project_name_simple = path_parts[3]
                    project_name = '/'.join(path_parts[0:4])

            if not project_name_simple:
                project_name_simple = project_name

            if not project_name or not project_name_re.match(project_name_simple):
                raise fev.Invalid(self.message('invalid', state), value, state)

        if not GoogleCodeProjectExtractor(project_name).check_readable():
            raise fev.Invalid(self.message('unavailable', state), value, state)
        return project_name


def split_project_name(project_name):
    '''
    For hosted projects, the project_name includes the hosted domain.  Split, like:

    :param str project_name: "a/eclipselabs.org/p/restclient-tool"
    :return: ``("/a/eclipselabs.org", "restclient-tool")``
    '''
    if project_name.startswith('a/'):
        hosted_domain_prefix = '/a/' + project_name.split('/')[1]
        project_name = project_name.split('/')[3]
    else:
        hosted_domain_prefix = ''
        project_name = project_name
    return hosted_domain_prefix, project_name


class GoogleCodeProjectExtractor(ProjectExtractor):
    BASE_URL = 'http://code.google.com'
    RE_REPO_TYPE = re.compile(r'(svn|hg|git)')

    PAGE_MAP = {
        'project_info': BASE_URL + '{hosted_domain_prefix}/p/{project_name}/',
        'source_browse': BASE_URL + '{hosted_domain_prefix}/p/{project_name}/source/browse/',
        'issues_csv': BASE_URL + '{hosted_domain_prefix}/p/{project_name}/issues/csv?can=1&colspec=ID&sort=ID&start={start}',
        'issue': BASE_URL + '{hosted_domain_prefix}/p/{project_name}/issues/detail?id={issue_id}',
    }

    LICENSE_MAP = defaultdict(lambda: 'Other/Proprietary License', {
        'Apache License 2.0': 'Apache License V2.0',
        'Artistic License/GPL': 'Artistic License',
        'Eclipse Public License 1.0': 'Eclipse Public License',
        'GNU GPL v2': 'GNU General Public License version 2.0 (GPLv2)',
        'GNU GPL v3': 'GNU General Public License version 3.0 (GPLv3)',
        'GNU Lesser GPL': 'GNU Library or Lesser General Public License version 2.0 (LGPLv2)',
        'MIT License': 'MIT License',
        'Mozilla Public License 1.1': 'Mozilla Public License 1.1 (MPL 1.1)',
        'New BSD License': 'BSD License',
        'Other Open Source': 'Open Software License',
    })

    DEFAULT_ICON = 'http://www.gstatic.com/codesite/ph/images/defaultlogo.png'

    def get_page_url(self, page_name, **kw):
        # override, to handle hosted domains
        hosted_domain_prefix, project_name = split_project_name(self.project_name)
        return self.PAGE_MAP[page_name].format(
            project_name=urllib.quote(project_name),
            hosted_domain_prefix=hosted_domain_prefix,
            **kw)

    def check_readable(self):
        resp = requests.head(self.get_page_url('project_info'))
        return resp.status_code == 200

    def get_short_description(self, project):
        page = self.get_page('project_info')
        project.short_description = page.find(
            itemprop='description').text.strip()

    def get_icon(self, project):
        page = self.get_page('project_info')
        icon_url = urljoin(self.url, page.find(itemprop='image').get('src'))
        if icon_url == self.DEFAULT_ICON:
            return
        icon_name = urllib.unquote(urlparse(icon_url).path).split('/')[-1]
        icon = File(icon_url, icon_name)
        filetype = icon.type
        # work around Google Code giving us bogus file type
        if filetype.startswith('text/html'):
            filetype = 'image/png'
        M.ProjectFile.save_image(
            icon_name, icon.file, filetype,
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta={'project_id': project._id, 'category': 'icon'})

    def get_license(self, project):
        page = self.get_page('project_info')
        license = page.find(text='Code license').findNext().find(
            'a').text.strip()
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
    def iter_issues(cls, project_name):
        """
        Iterate over all issues for a project,
        using paging to keep the responses reasonable.
        """
        extractor = cls(project_name)
        issue_ids = extractor.get_issue_ids(start=0)
        while issue_ids:
            for issue_id in sorted(issue_ids):
                try:
                    yield (int(issue_id), cls(project_name, 'issue', issue_id=issue_id))
                except HTTPError as e:
                    if e.code == 404:
                        log.warn('Unable to load GC issue: %s #%s: %s: %s',
                                 project_name, issue_id, e, e.url)
                        continue
                    else:
                        raise
            # get any new issues that were created while importing
            # (jumping back a few in case some were deleted and new ones added)
            new_ids = extractor.get_issue_ids(start=len(issue_ids) - 10)
            issue_ids = new_ids - issue_ids

    def get_issue_ids(self, start=0):
        limit = 100

        issue_ids = set()
        page = self.get_page('issues_csv', parser=csv_parser, start=start)
        while page:
            if len(page) <= 0:
                return
            issue_ids.update(page)
            start += limit
            page = self.get_page('issues_csv', parser=csv_parser, start=start)
        return issue_ids

    def get_issue_summary(self):
        text = self.page.find(id='issueheader').findAll(
            'td', limit=2)[1].span.text.strip()
        bs = BeautifulSoup(text, convertEntities=BeautifulSoup.HTML_ENTITIES)
        return bs.text

    def get_issue_description(self):
        return _as_markdown(self.page.find(id='hc0').pre, self.project_name)

    def get_issue_created_date(self):
        return self.page.find(id='hc0').find('span', 'date').get('title')

    def get_issue_mod_date(self):
        comments = self.page.findAll('div', 'issuecomment')
        if comments:
            last_update = Comment(comments[-1], self.project_name)
            return last_update.created_date
        else:
            return self.get_issue_created_date()

    def get_issue_creator(self):
        a = self.page.find(id='hc0').find(True, 'userlink')
        return UserLink(a)

    def get_issue_status(self):
        tag = self.page.find(id='issuemeta').find(
            'th', text=re.compile('Status:')).findNext().span
        if tag:
            return tag.text.strip()
        else:
            return ''

    def get_issue_owner(self):
        tag = self.page.find(id='issuemeta').find(
            'th', text=re.compile('Owner:')).findNext().find(True, 'userlink')
        if tag:
            return UserLink(tag)
        else:
            return None

    def get_issue_labels(self):
        label_nodes = self.page.find(id='issuemeta').findAll('a', 'label')
        return [_as_text(l) for l in label_nodes]

    def get_issue_attachments(self):
        return _get_attachments(self.page.find(id='hc0'))

    def get_issue_stars(self):
        stars_re = re.compile(r'(\d+) (person|people) starred this issue')
        stars = self.page.find(id='issueheader').find(text=stars_re)
        if stars:
            return int(stars_re.search(stars).group(1))
        return 0

    def iter_comments(self):
        for comment in self.page.findAll('div', 'issuecomment'):
            yield Comment(comment, self.project_name)


class UserLink(object):

    def __init__(self, tag):
        self.name = tag.text.strip()
        if tag.get('href'):
            self.url = urljoin(
                GoogleCodeProjectExtractor.BASE_URL, tag.get('href'))
        else:
            self.url = None

    def __str__(self):
        if self.url:
            return '[{name}]({url})'.format(name=self.name, url=self.url)
        else:
            return self.name


def _get_attachments(tag):
    attachment_links = tag.find('div', 'attachments')
    if attachment_links:
        attachments = []
        for a in attachment_links.findAll('a', text='Download'):
            url = a.parent.get('href')
            try:
                attachment = Attachment(url)
            except Exception:
                log.exception('Could not get attachment: %s', url)
            else:
                attachments.append(attachment)
        return attachments
    else:
        return []


class Comment(object):

    def __init__(self, tag, project_name):
        self.author = UserLink(
            tag.find('span', 'author').find(True, 'userlink'))
        self.created_date = tag.find('span', 'date').get('title')
        self.body = _as_markdown(tag.find('pre'), project_name)
        self._get_updates(tag)
        self.attachments = _get_attachments(tag)

    def _get_updates(self, tag):
        _updates = tag.find('div', 'updates')
        self.updates = {
            b.text: b.nextSibling.strip()
            for b in _updates.findAll('b')} if _updates else {}

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
            body=self.body,
            updates='\n'.join(
                '**%s** %s' % (k, v)
                for k, v in self.updates.items()
            ),
        )
        return text


class Attachment(File):

    def __init__(self, url):
        url = urljoin(GoogleCodeProjectExtractor.BASE_URL, url)
        filename = parse_qs(urlparse(url).query)['name'][0]
        super(Attachment, self).__init__(url, filename)
