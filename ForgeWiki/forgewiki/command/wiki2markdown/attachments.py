import os
import json

from ming.orm.ormsession import ThreadLocalORMSession

from forgewiki.command.wiki2markdown.base import BaseImportUnit

from allura.command import base as allura_base

from pylons import c

from allura import model as M
from forgewiki import model as WM
from forgewiki import converters

class AttachmentsImportUnit(BaseImportUnit):
    def _export_pages(self, p):
        if p.neighborhood is None:
            return
        wiki_app = p.app_instance('wiki')
        discussion_app = p.app_instance('discussion')

        pid = "%s" % p._id
        out_dir = os.path.join(self.options.output_dir, pid)
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)

        file_path = os.path.join(out_dir, "attachments.json")
        json_attachments = {'pages': {}, 'discuss': {}}

        if wiki_app is not None:
            pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        else:
            pages = []
        for page in pages:
            page_id = "%s" % page._id

            attachments_list = page.attachments.all()
            if len(attachments_list) == 0:
                continue

            page_text = page.text
            for att in attachments_list:
                if att.content_type[:5] == "image":
                    page_text = '%s\n![%s](%s "%s")' % (page_text,
                                          att.filename,
                                          att.url(),
                                          att.filename
                                          )
                else:
                    page_text = '%s\n[%s](%s)' % (page_text,
                                          att.filename,
                                          att.url()
                                          )
            json_attachments['pages'][page_id] = {'text': page_text}

        if discussion_app is not None:
            discussions = M.Discussion.query.find(app_config_id=discussion_app.config._id).all()
        else:
            discussions = []
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id

                attachments_list = post.attachments.all()
                if len(attachments_list) == 0:
                    continue

                post_text = post.text
                for att in attachments_list:
                    if att.content_type[:5] == "image":
                        post_text = '%s\n![%s](%s "%s")' % (post_text,
                                          att.filename,
                                          att.url(),
                                          att.filename
                                          )
                    else:
                        post_text = '%s\n[%s](%s)' % (post_text,
                                          att.filename,
                                          att.url()
                                          )
                json_attachments['discuss'][post_id] = {'text': post_text}

        if len(json_attachments['pages']) > 0 or len(json_attachments['discuss']) > 0:
            with open(file_path, 'w') as attachments_file:
                json.dump(json_attachments, attachments_file)

    def _load_pages(self, p):
        if p.neighborhood is None:
            return
        wiki_app = p.app_instance('wiki')
        discussion_app = p.app_instance('discussion')

        pid = "%s" % p._id
        file_path = os.path.join(self.options.output_dir, pid, "attachments.json")
        if not os.path.isfile(file_path):
            return

        c.project = None
        json_attachments = {'pages': {}, 'discuss': {}}
        with open(file_path, 'r') as attachments_file:
            json_attachments = json.load(attachments_file)

        if wiki_app is not None:
            pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        else:
            pages = []
        for page in pages:
            page_id = "%s" % page._id

            if page_id in json_attachments['pages']:
                page.text = json_attachments['pages'][page_id]['text']

        if discussion_app is not None:
            discussions = M.Discussion.query.find(app_config_id=discussion_app.config._id).all()
        else:
            discussions = []
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id

                if post_id in json_attachments['discuss']:
                    post.text = json_attachments['discuss'][post_id]['text']

        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def extract(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._export_pages(p)
        allura_base.log.info("Export attachments complete")

    def load(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._load_pages(p)
        allura_base.log.info("Load attachments complete")
