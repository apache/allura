import os
import json

from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from forgewiki import model as WM
from forgewiki.converters import mediawiki2markdown
from allura.command import base as allura_base
from allura.lib import helpers as h


class MediawikiLoader(object):
    """Load MediaWiki data from json to Allura wiki tool"""

    def __init__(self, options):
        self.options = options
        self.nbhd = M.Neighborhood.query.get(name=options.nbhd)
        if not self.nbhd:
            allura_base.log.error("Can't find neighborhood with name %s"
                                  % options.nbhd)
            exit(2)
        self.project = M.Project.query.get(shortname=options.project,
                                           neighborhood_id=self.nbhd._id)
        if not self.project:
            allura_base.log.error("Can't find project with shortname %s "
                                  "and neighborhood_id %s"
                                  % (options.project, self.nbhd._id))
            exit(2)

        self.wiki = self.project.app_instance('wiki')
        if not self.wiki:
            allura_base.log.error("Can't find wiki app in given project")
            exit(2)

    def load(self):
        self.load_pages()
        self.load_history()
        self.load_talk()
        self.load_attachments()

    def _pages(self):
        """Yield page_data for next wiki page"""
        h.set_context(self.project.shortname, 'wiki', neighborhood=self.nbhd)
        pages_dir = os.path.join(self.options.dump_dir, 'pages')
        page_files = []
        if os.path.isdir(pages_dir):
            page_files = os.listdir(pages_dir)
        for filename in page_files:
            file_path = os.path.join(pages_dir, filename)
            with open(file_path, 'r') as pages_file:
                page_data = json.load(pages_file)
            yield page_data

    def load_pages(self):
        allura_base.log.info('Loading pages into allura...')
        for page in self._pages():
            if page['title'] == 'Main_Page':
                gl = WM.Globals.query.get(app_config_id=self.wiki.config._id)
                if gl is not None:
                    gl.root = page['title']
            p = WM.Page.upsert(page['title'])
            p.viewable_by = ['all']
            p.text = mediawiki2markdown(page['text'])
            if not p.history().first():
                p.commit()

        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        allura_base.log.info('Loading pages done')

    def load_history(self):
        allura_base.log.info('load_history not implemented yet. Skip.')

    def load_talk(self):
        allura_base.log.info('load_talk not implemented yet. Skip.')

    def load_attachments(self):
        allura_base.log.info('load_attachments not implemented yet. Skip.')
