from pylons import c
from docutils.core import publish_parts
import re

import pymongo
from ming import Document
from ming import schema as S

from pyforge.model import ProjectSession

wikiwords = [
    (r'\b([A-Z]\w+[A-Z]+\w+)', r'<a href="../\1/">\1</a>'),
    (r'([^\\])\[(.*)\]', r'\1<a href="../\2/">\2</a>'),
    (r'\\\[(.*)\]', r'[\1]'),
    (r'^\[(.*)\]', r'<a href="../\1/">\1</a>'),
    ]
wikiwords = [
    (re.compile(pattern), replacement)
    for pattern, replacement in wikiwords ]

class Page(Document):
    class __mongometa__:
        session = ProjectSession()
        name='page'
        schema=dict(
            _id=S.ObjectId(),
            project_id=str,
            version=int,
            title=str,
            text=str,
            )

    @classmethod
    def upsert(cls, title, version=None):
        q = dict(
            project_id=c.project._id,
            title=title)
        if version is not None:
            q['version'] = version
        versions = cls.m.find(q)
        if not versions.count():
            return cls.make(dict(
                    project_id=c.project._id,
                    title=title,
                    text='',
                    version=0))
        latest = max(versions, key=lambda v:v.version)
        new_obj=dict(latest, version=latest.version + 1)
        del new_obj['_id']
        return cls.make(new_obj)

    @classmethod
    def history(cls, title):
        history = cls.m.find(
            dict(project_id=c.project._id, title=title))
        history = history.sort('version', pymongo.DESCENDING)
        return history

    @property
    def html_text(self):
        content = publish_parts(self.text, writer_name='html')['html_body']
        for pattern, replacement in wikiwords:
            content = pattern.sub(replacement, content)
        return content

