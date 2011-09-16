"""
Generate Allura sitemap xml files.

$ paster script production.ini ../scripts/create-allura-sitemap.py

Output files will be created in ./allura_sitemap.
"""
import os, sys
from datetime import datetime
from jinja2 import Template
from pylons import c

from allura import model as M

OUTPUT_DIR = 'allura_sitemap'
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

def main():
    cwd = os.getcwd()
    output_path = os.path.join(cwd, OUTPUT_DIR)
    if os.path.exists(output_path):
        sys.exit('%s directory already exists.' % output_path)
    try:
        os.mkdir(output_path)
    except OSError, e:
        sys.exit("Couldn't create %s: %s" % (output_path, e))

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
    for offset in offsets:
        locs = []
        for p in M.Project.query.find().skip(offset).limit(PROJECTS_PER_FILE):
            c.project = p
            locs += [BASE_URL + s.url for s in p.sitemap()]
        sitemap_vars = dict(now=now, locs=locs)
        sitemap_content = Template(SITEMAP_TEMPLATE).render(sitemap_vars)
        with open(os.path.join(output_path, 'sitemap-%d.xml' % offset), 'w') as f:
            f.write(sitemap_content)

if __name__ == '__main__':
    main()
