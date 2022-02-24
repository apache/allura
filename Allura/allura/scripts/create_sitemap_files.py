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

"""
Generate Allura sitemap xml files.  You will need to configure your webserver to serve the files.

This takes a while to run on a prod-sized data set. There are a couple of
things that would make it faster, if we need/want to.

1. Monkeypatch forgetracker.model.ticket.Globals.bin_count to skip the
   refresh (Solr search) and just return zero for everything, since we don't
   need bin counts for the sitemap.

2. Use multiprocessing to distribute the offsets to n subprocesses.
"""

import os
from datetime import datetime
import argparse

from jinja2 import Template
import tg
import webob
from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession
from tg import config

from allura import model as M
from allura.lib import security, utils
from allura.scripts import ScriptTask


MAX_SITEMAP_URLS = 50000

INDEX_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   {% for sitemap in sitemaps -%}
   <sitemap>
      <loc>{{ sitemap }}</loc>
      <lastmod>{{ now }}</lastmod>
   </sitemap>
   {%- endfor %}
</sitemapindex>
"""

SITEMAP_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    {% for loc in locs -%}
    <url>
        <loc>{{ loc.url }}</loc>
        <lastmod>{{ loc.date }}</lastmod>
        <changefreq>daily</changefreq>
    </url>
    {% endfor %}
</urlset>
"""


class CreateSitemapFiles(ScriptTask):

    @classmethod
    def execute(cls, options):
        # This script will indirectly call app.sidebar_menu() for every app in
        # every project. Some of the sidebar_menu methods expect the
        # tg.request threadlocal object to be present. So, we're faking it.
        #
        # The fact that this isn't a 'real' request doesn't matter for the
        # purposes of the sitemap.
        tg.request_local.context.request = webob.Request.blank('/')

        output_path = options.output_dir
        if os.path.exists(output_path):
            raise Exception('%s directory already exists.' % output_path)
        os.mkdir(output_path)

        now = datetime.utcnow().date()
        sitemap_content_template = Template(SITEMAP_TEMPLATE)

        def write_sitemap(urls, file_no):
            sitemap_content = sitemap_content_template.render(dict(now=now, locs=urls))
            with open(os.path.join(output_path, 'sitemap-%d.xml' % file_no), 'w') as f:
                f.write(sitemap_content)

        creds = security.Credentials.get()
        locs = []
        file_count = 0

        excl_nbhd_ids = []
        if options.exclude_neighborhoods:
            prefix = ['/%s/' % n for n in options.exclude_neighborhoods]
            excl_nbhd_ids = [nbhd._id for nbhd in M.Neighborhood.query.find({'url_prefix': {'$in': prefix}})]

        # write sitemap files, MAX_SITEMAP_URLS per file
        for chunk in utils.chunked_find(M.Project, {'deleted': False, 'neighborhood_id': {'$nin': excl_nbhd_ids}}):
            for p in chunk:
                c.project = p
                try:
                    for s in p.sitemap(excluded_tools=options.exclude_tools, xml=True):
                        url = config['base_url'] + s.url if s.url[0] == '/' else s.url
                        locs.append({'url': url,
                                     'date': p.last_updated.strftime("%Y-%m-%d")})

                except Exception as e:
                    print("Error creating sitemap for project '%s': %s" %\
                        (p.shortname, e))
                creds.clear()
                if len(locs) >= options.urls_per_file:
                    write_sitemap(locs[:options.urls_per_file], file_count)
                    del locs[:options.urls_per_file]
                    file_count += 1
                M.main_orm_session.clear()
            ThreadLocalORMSession.close_all()
        while locs:
            write_sitemap(locs[:options.urls_per_file], file_count)
            del locs[:options.urls_per_file]
            file_count += 1
        # write sitemap index file
        if file_count:
            sitemap_index_vars = dict(
                now=now,
                sitemaps=[
                    '%s%s/sitemap-%d.xml' % (config['base_url'], options.url_dir, n)
                    for n in range(file_count)])
            sitemap_index_content = Template(
                INDEX_TEMPLATE).render(sitemap_index_vars)
            with open(os.path.join(output_path, 'sitemap.xml'), 'w') as f:
                f.write(sitemap_index_content)

    @classmethod
    def parser(cls):
        class Validate(argparse.Action):
            def __call__(self, parser, namespace, value, option_string=None):
                value = min(value, MAX_SITEMAP_URLS)
                setattr(namespace, self.dest, value)

        parser = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('-o', '--output-dir',
                            dest='output_dir',
                            default='/tmp/allura_sitemap',
                            help='Output directory (absolute path).'
                                  '[default: %(default)s]')
        parser.add_argument('-u', '--urls-per-file', dest='urls_per_file',
                            default=10000, type=int,
                            help='Number of URLs per sitemap file. [default: %(default)s, max: ' +
                            str(MAX_SITEMAP_URLS) + ']',
                            action=Validate)
        parser.add_argument('--exclude-neighborhood', '-n', '--neighborhood', dest='exclude_neighborhoods',
                            help="URL prefix of excluded neighborhood(s)  Example: u",
                            default=None, nargs='*', metavar='N')
        parser.add_argument('--exclude-tools', dest='exclude_tools',
                            help="URL prefix of excluded neighborhood(s)",
                            default=['link', 'git', 'hg', 'svn'],
                            nargs='*', metavar='TOOL')
        parser.add_argument('--url-dir', dest='url_dir',
                            default='/allura_sitemap',
                            help='URL directory in which the files will be served from')
        return parser


def get_parser():
    return CreateSitemapFiles.parser()


if __name__ == '__main__':
    CreateSitemapFiles.main()
