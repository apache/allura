"""
Generate Allura sitemap xml files.
"""

import os, sys
from datetime import datetime
from jinja2 import Template
from pylons import c

from allura import model as M
from allura.lib import security
from ming.orm import session, ThreadLocalORMSession

PROJECTS_PER_FILE = 1000
BASE_URL = 'http://sourceforge.net'

INDEX_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   {% for sitemap in sitemaps -%}
   <sitemap>
      <loc>{{ sitemap }}</loc>
      <lastmod>{{ now }}</lastmod>
      <changefreq>daily</changefreq>
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
    output_path = options.output_dir
    if os.path.exists(output_path):
        sys.exit('Error: %s directory already exists.' % output_path)
    try:
        os.mkdir(output_path)
    except OSError, e:
        sys.exit("Error: Couldn't create %s:\n%s" % (output_path, e))

    # Count projects and create sitemap index file
    num_projects = M.Project.query.find().count()
    now = datetime.utcnow().date()
    offsets = [i for i in range(0, num_projects, PROJECTS_PER_FILE)]
    sitemap_index_vars = dict(
        now=now,
        sitemaps = [
            '%s/allura_sitemap/sitemap-%d.xml' % (BASE_URL, offset)
            for offset in offsets])
    sitemap_index_content = Template(INDEX_TEMPLATE).render(sitemap_index_vars)
    with open(os.path.join(output_path, 'sitemap.xml'), 'w') as f:
        f.write(sitemap_index_content)

    # Create urlset file for each chunk of PROJECTS_PER_FILE projects
    sitemap_content_template = Template(SITEMAP_TEMPLATE)
    creds = security.Credentials.get()
    for offset in offsets:
        locs = []
        for p in M.Project.query.find().skip(offset).limit(PROJECTS_PER_FILE):
            c.project = p
            try:
                locs += [BASE_URL + s.url for s in p.sitemap()]
            except Exception, e:
                print "Error creating sitemap for project '%s': %s" %\
                      (p.shortname, e)
            creds.clear()
        sitemap_vars = dict(now=now, locs=locs)
        sitemap_content = sitemap_content_template.render(sitemap_vars)
        with open(os.path.join(output_path, 'sitemap-%d.xml' % offset), 'w') as f:
            f.write(sitemap_content)
        session(p).clear()
        ThreadLocalORMSession.close_all()

def parse_options():
    from optparse import OptionParser
    optparser = OptionParser(
        usage='allurapaste script /var/local/config/production.ini '
              '-- %prog [OPTIONS]')
    optparser.add_option('-o', '--output-dir', dest='output_dir',
                         default='/tmp/allura_sitemap',
                         help='Output directory (absolute path).'
                              'Default is /tmp/allura_sitemap.')
    options, args = optparser.parse_args()
    return options, args

if __name__ == '__main__':
    options, args = parse_options()
    main(options, args)
