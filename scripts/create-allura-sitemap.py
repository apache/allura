"""
Generate Allura sitemap xml files.

This takes a while to run on a prod-sized data set. There are a couple of
things that would make it faster, if we need/want to.

1. Monkeypatch forgetracker.model.ticket.Globals.bin_count to skip the
   refresh (Solr search) and just return zero for everything, since we don't
   need bin counts for the sitemap.

2. Use multiprocessing to distribute the offsets to n subprocesses.
"""

import os, sys
from datetime import datetime
from jinja2 import Template

import pylons, webob
from pylons import c

from allura import model as M
from allura.lib import security, utils
from ming.orm import session, ThreadLocalORMSession

MAX_SITEMAP_URLS = 50000
BASE_URL = 'http://sourceforge.net'

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
        <loc>{{ loc }}</loc>
        <lastmod>{{ now }}</lastmod>
        <changefreq>daily</changefreq>
    </url>
    {% endfor %}
</urlset>
"""

def main(options, args):
    # This script will indirectly call app.sidebar_menu() for every app in
    # every project. Some of the sidebar_menu methods expect the
    # pylons.request threadlocal object to be present. So, we're faking it.
    #
    # The fact that this isn't a 'real' request doesn't matter for the
    # purposes of the sitemap.
    pylons.request._push_object(webob.Request.blank('/'))

    output_path = options.output_dir
    if os.path.exists(output_path):
        sys.exit('Error: %s directory already exists.' % output_path)
    try:
        os.mkdir(output_path)
    except OSError, e:
        sys.exit("Error: Couldn't create %s:\n%s" % (output_path, e))

    now = datetime.utcnow().date()
    sitemap_content_template = Template(SITEMAP_TEMPLATE)
    def write_sitemap(urls, file_no):
        sitemap_content = sitemap_content_template.render(dict(
            now=now, locs=urls))
        with open(os.path.join(output_path, 'sitemap-%d.xml' % file_no), 'w') as f:
            f.write(sitemap_content)

    creds = security.Credentials.get()
    locs = []
    file_count = 0
    # write sitemap files, MAX_SITEMAP_URLS per file
    for chunk in utils.chunked_find(M.Project):
        for p in chunk:
            c.project = p
            try:
                locs += [BASE_URL + s.url if s.url[0] == '/' else s.url
                        for s in p.sitemap(excluded_tools=['git', 'hg', 'svn'])]
            except Exception, e:
                print "Error creating sitemap for project '%s': %s" %\
                    (p.shortname, e)
            creds.clear()
            if len(locs) >= options.urls_per_file:
                write_sitemap(locs[:options.urls_per_file], file_count)
                del locs[:options.urls_per_file]
                file_count += 1
            session(p).clear()
        ThreadLocalORMSession.close_all()
    while locs:
        write_sitemap(locs[:options.urls_per_file], file_count)
        del locs[:options.urls_per_file]
        file_count += 1
    # write sitemap index file
    if file_count:
        sitemap_index_vars = dict(
            now=now,
            sitemaps = [
                '%s/allura_sitemap/sitemap-%d.xml' % (BASE_URL, n)
                for n in range(file_count)])
        sitemap_index_content = Template(INDEX_TEMPLATE).render(sitemap_index_vars)
        with open(os.path.join(output_path, 'sitemap.xml'), 'w') as f:
            f.write(sitemap_index_content)

def parse_options():
    def validate(option, opt_str, value, parser):
        parser.values.urls_per_file = min(value, MAX_SITEMAP_URLS)

    from optparse import OptionParser
    optparser = OptionParser(
        usage='allurapaste script /var/local/config/production.ini '
              '-- %prog [OPTIONS]')
    optparser.add_option('-o', '--output-dir', dest='output_dir',
                         default='/tmp/allura_sitemap',
                         help='Output directory (absolute path).'
                              '[default: %default]')
    optparser.add_option('-u', '--urls-per-file', dest='urls_per_file',
                         default=10000, type='int',
                         help='Number of URLs per sitemap file. '
                         '[default: %default, max: ' +
                         str(MAX_SITEMAP_URLS) + ']',
                         action='callback', callback=validate)
    options, args = optparser.parse_args()
    return options, args

if __name__ == '__main__':
    options, args = parse_options()
    main(options, args)
