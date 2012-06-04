import os
import json

from forgewiki.command.wiki2markdown.base import BaseImportUnit

from allura.command import base as allura_base

from allura import model as M
from forgewiki import converters

class TalkImportUnit(BaseImportUnit):
    def _export_pages(self, p):
        if p.neighborhood is None:
            return
        discussion_app = p.app_instance('discussion')
        if discussion_app is None:
            return

        pid = "%s" % p._id
        out_dir = os.path.join(self.options.output_dir, pid)
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)

        file_path = os.path.join(out_dir, "talk.json")

        json_talk = {}
        discussions = M.Discussion.query.find(app_config_id=discussion_app.config._id).all()
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id
                json_talk[post_id] = {'text': converters.mediawiki2markdown(post.text), 'history': {}}
                for hist in M.PostHistory.query.find(dict(artifact_id=post._id)).all():
                    hist_id = "%s" % hist._id
                    json_talk[post_id]['history'][hist_id] = {'text': converters.mediawiki2markdown(hist.data['text'])}

        if len(json_talk) > 0:
            with open(file_path, 'w') as talk_file:
                json.dump(json_talk, talk_file)

    def _load_pages(self, p):
        pass

    def extract(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._export_pages(p)
        allura_base.log.info("Export talk complete")

    def load(self):
        projects = M.Project.query.find().all()
        for p in projects:
            self._load_pages(p)
        allura_base.log.info("Load talk complete")
