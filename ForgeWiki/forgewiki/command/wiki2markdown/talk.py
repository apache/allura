import os
import json

from ming.orm.ormsession import ThreadLocalORMSession

from forgewiki.command.wiki2markdown.base import BaseImportUnit

from allura.command import base as allura_base

from pylons import c

from allura import model as M
from forgediscussion import model as DM
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
        discussions = DM.Forum.query.find(app_config_id=discussion_app.config._id).all()
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id
                json_talk[post_id] = {'text': converters.mediawiki2markdown(post.text), 'history': {}}
                for hist in post.history().all():
                    hist_id = "%s" % hist._id
                    json_talk[post_id]['history'][hist_id] = {'text': converters.mediawiki2markdown(hist.data['text'])}

        if len(json_talk) > 0:
            with open(file_path, 'w') as talk_file:
                json.dump(json_talk, talk_file)

    def _load_pages(self, p):
        if p.neighborhood is None:
            return
        discussion_app = p.app_instance('discussion')
        if discussion_app is None:
            return

        pid = "%s" % p._id
        file_path = os.path.join(self.options.output_dir, pid, "talk.json")
        if not os.path.isfile(file_path):
            return

        json_talk = {}
        with open(file_path, 'r') as talk_file:
            json_talk = json.load(talk_file)

        c.project = None

        discussions = DM.Forum.query.find(app_config_id=discussion_app.config._id).all()
        for discuss in discussions:
            for post in discuss.posts:
                post_id = "%s" % post._id
                if post_id not in json_talk:
                    continue

                post.text = json_talk[post_id]['text']
                for hist in post.history().all():
                    hist_id = "%s" % hist._id
                    if hist_id in json_talk[post_id]['history']:
                        hist.data['text'] = json_talk[post_id]['history'][hist_id]['text']

        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

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
