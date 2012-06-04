import os
import json

from ming.orm.ormsession import ThreadLocalORMSession

from forgewiki.command.wiki2markdown.base import BaseImportUnit

from allura.command import base as allura_base

from pylons import c

from allura import model as M
from forgewiki import model as WM
from forgewiki import converters

class HistoryImportUnit(BaseImportUnit):
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

        file_path = os.path.join(out_dir, "history.json")

        json_history = {}
        pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        for page in pages:
            for hist in WM.PageHistory.query.find(dict(artifact_id=page._id)).all():
                hist_id = "%s" % hist._id
                json_history[hist_id] = {'text': converters.mediawiki2markdown(hist.data['text'])}

        if len(json_history) > 0:
            with open(file_path, 'w') as history_file:
                json.dump(json_history, history_file)

    def _load_pages(self, p):
        if p.neighborhood is None:
            return
        wiki_app = p.app_instance('wiki')
        if wiki_app is None:
            return

        pid = "%s" % p._id
        file_path = os.path.join(self.options.output_dir, pid, "history.json")
        if not os.path.isfile(file_path):
            return

        json_history = {}
        with open(file_path, 'r') as history_file:
            json_history = json.load(history_file)

        c.project = None
        pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        for page in pages:
            for hist in WM.PageHistory.query.find(dict(artifact_id=page._id)).all():
                hist_id = "%s" % hist._id
                if hist_id in json_history:
                    hist.data['text'] = json_history[hist_id]['text']
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
