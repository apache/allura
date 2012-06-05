import os
import json
from bson import ObjectId

from ming.orm.ormsession import ThreadLocalORMSession

from forgewiki.command.wiki2markdown.base import BaseImportUnit

from allura.command import base as allura_base

from pylons import c

from allura.lib import helpers as h
from allura import model as M
from forgewiki import model as WM
from forgewiki import converters


class PagesImportUnit(BaseImportUnit):
    def _export_pages(self, p):
        if p.neighborhood is None:
            return
        wiki_app = p.app_instance('wiki')
        discussion_app = p.app_instance('discussion')

        pid = "%s" % p._id
        out_dir = os.path.join(self.options.output_dir, pid)
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)

        file_path = os.path.join(out_dir, "pages.json")

        json_pages = {'pages': {}, 'discuss': {}}
        if wiki_app is not None:
            pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        else:
            pages = []
        for page in pages:
            page_id = "%s" % page._id
            json_pages['pages'][page_id] = {'text': converters.mediawiki2markdown(page.text)}

        if discussion_app is not None:
            discussions = M.Discussion.query.find(app_config_id=discussion_app.config._id).all()
        else:
            discussions = []
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id
                json_pages['discuss'][post_id] = {'text': converters.mediawiki2markdown(post.text)}

        if len(json_pages['pages']) > 0 or len(json_pages['discuss']) > 0:
            with open(file_path, 'w') as pages_file:
                json.dump(json_pages, pages_file)

    def _load_pages(self, p):
        if p.neighborhood is None:
            return
        wiki_app = p.app_instance('wiki')
        discussion_app = p.app_instance('discussion')

        pid = "%s" % p._id
        file_path = os.path.join(self.options.output_dir, pid, "pages.json")
        if not os.path.isfile(file_path):
            return

        json_pages = {}
        with open(file_path, 'r') as pages_file:
            json_pages = json.load(pages_file)

        c.project = None

        if wiki_app is not None:
            pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        else:
            pages = []
        for page in pages:
            page_id = "%s" % page._id
            if page_id in json_pages['pages']:
                page.text = json_pages['pages'][page_id]['text']

        if discussion_app is not None:
            discussions = M.Discussion.query.find(app_config_id=discussion_app.config._id).all()
        else:
            discussions = []
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id
                if post_id in json_pages['discuss']:
                    post.text = json_pages['discuss'][post_id]['text']

        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def extract(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._export_pages(p)
        allura_base.log.info("Export pages complete")

    def load(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._load_pages(p)
        allura_base.log.info("Load pages complete")
