import os
import json

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
        if wiki_app is None:
            return

        pid = "%s" % p._id
        out_dir = os.path.join(self.options.output_dir, pid)
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)

        file_path = os.path.join(out_dir, "attachments.json")
        json_attachments = {'pages': {}, 'discuss': {}}
        pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
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

    def extract(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._export_pages(p)
        allura_base.log.info("Export attachments complete")

    def load(self):
        raise NotImplementedError('add here data loading')
