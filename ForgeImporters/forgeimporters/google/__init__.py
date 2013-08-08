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
import urllib2
from urlparse import urlparse, urljoin
from collections import defaultdict
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import logging

from BeautifulSoup import BeautifulSoup

from allura import model as M


log = logging.getLogger(__name__)

class GoogleCodeProjectExtractor(object):
    BASE_URL = 'http://code.google.com'
    RE_REPO_TYPE = re.compile(r'(svn|hg|git)')

    PAGE_MAP = {
            'project_info': BASE_URL + '/p/%s/',
            'source_browse': BASE_URL + '/p/%s/source/browse/',
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

    def __init__(self, allura_project, gc_project_name, page=None):
        self.project = allura_project
        self.gc_project_name = gc_project_name
        self._page_cache = {}
        self.url = None
        self.page = None
        if page:
            self.get_page(page)

    def get_page(self, page_name_or_url):
        """Return a Beautiful soup object for the given page name or url.

        If a page name is provided, the associated url is looked up in
        :attr:`PAGE_MAP`.

        Results are cached so that subsequent calls for the same page name or
        url will return the cached result rather than making another HTTP
        request.

        """
        if page_name_or_url in self._page_cache:
            return self._page_cache[page_name_or_url]
        self.url = (self.get_page_url(page_name_or_url) if page_name_or_url in
                self.PAGE_MAP else page_name_or_url)
        self.page = self._page_cache[page_name_or_url] = \
                BeautifulSoup(urllib2.urlopen(self.url))
        return self.page

    def get_page_url(self, page_name):
        """Return the url associated with ``page_name``.

        Raises KeyError if ``page_name`` is not in :attr:`PAGE_MAP`.

        """
        return self.PAGE_MAP[page_name] % urllib.quote(self.gc_project_name)

    def get_short_description(self):
        page = self.get_page('project_info')
        self.project.short_description = page.find(itemprop='description').string.strip()

    def get_icon(self):
        page = self.get_page('project_info')
        icon_url = urljoin(self.url, page.find(itemprop='image').attrMap['src'])
        if icon_url == self.DEFAULT_ICON:
            return
        icon_name = urllib.unquote(urlparse(icon_url).path).split('/')[-1]
        fp_ish = urllib2.urlopen(icon_url)
        fp = StringIO(fp_ish.read())
        M.ProjectFile.save_image(
            icon_name, fp,
            fp_ish.info()['content-type'].split(';')[0],  # strip off charset=x extra param,
            square=True, thumbnail_size=(48,48),
            thumbnail_meta={'project_id': self.project._id, 'category': 'icon'})

    def get_license(self):
        page = self.get_page('project_info')
        license = page.find(text='Code license').findNext().find('a').string.strip()
        trove = M.TroveCategory.query.get(fullname=self.LICENSE_MAP[license])
        self.project.trove_license.append(trove._id)

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
