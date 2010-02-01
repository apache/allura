from time import sleep
from datetime import datetime

from pylons import g #g is a namespace for globally accessable app helpers
from pylons import c as context
import re

from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.base import state, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.model import VersionedArtifact, Snapshot, Message

wikiwords = [
    (r'\b([A-Z]\w+[A-Z]+\w+)', r'<a href="../\1/">\1</a>'),
    ]

wikiwords = [
    (re.compile(pattern), replacement)
    for pattern, replacement in wikiwords ]

def to_html(text):
    content = g.markdown.convert(text)
    for pattern, replacement in wikiwords:
        content = pattern.sub(replacement, content)
    return content

class PageHistory(Snapshot):
    class __mongometa__:
        name='page_history'

    def original(self):
        return Page.query.get(_id=self.artifact_id)
        
    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        result.update(
            title_s='Version %d of %s' % (
                self.version,self.original().title),
            type_s='WikiPage Snapshot',
            text=self.data.text)
        return result

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return to_html(self.data.text)

    def root_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(page_id=self.artifact_id, parent_id=None))
        else:
            return []

class Page(VersionedArtifact):
    class __mongometa__:
        name='page'
        history_class = PageHistory

    title=FieldProperty(str)
    text=FieldProperty(schema.String, if_missing='')

    def url(self):
        return self.app_config.url() + self.title + '/'

    def shorthand_id(self):
        return self.title

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title_s='WikiPage %s' % self.title,
            version_i=self.version,
            type_s='WikiPage',
            text=self.text)
        return result
    
    @classmethod
    def upsert(cls, title, version=None):
        """Update page with `title` or insert new page with that name"""
        if version is None:
            q = dict(
                project_id=context.project._id,
                title=title)
            #Check for existing page object    
            obj = cls.query.get(
                app_config_id=context.app.config._id,
                title=title)
            if obj is None:
                obj = cls(
                    title=title,
                    app_config_id=context.app.config._id,
                    )
            return obj
        else:
            pg = cls.upsert(title)
            HC = cls.__mongometa__.history_class
            ss = HC.query.find({'artifact_id':pg._id, 'version':int(version)}).one()
            return ss

    def reply(self):
        while True:
            try:
                c = Comment(page_id=self._id)
                return c
            except OperationFailure:
                sleep(0.1)
                continue

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return to_html(self.text)

    def root_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(page_id=self._id, parent_id=None))
        else:
            return []

class Comment(Message):
    class __mongometa__:
        name='comment'
    page_id=FieldProperty(schema.ObjectId)

    def index(self):
        result = Message.index(self)
        author = self.author()
        result.update(
            title_s='Comment on page %s by %s' % (
                self.page.title, author.display_name),
            type_s='Comment on WikiPage',
            page_title_t=self.page.title)
        return result

    @property
    def page(self):
        """The page this comment connects too"""
        return Page.query.get(_id=self.page_id)

    @property
    def posted_ago(self):
        comment_td = (datetime.utcnow() - self.timestamp)
        if comment_td.seconds < 3600 and comment_td.days < 1:
            return "%s minutes ago" % (comment_td.seconds / 60)
        elif comment_td.seconds >= 3600 and comment_td.days < 1:
            return "%s hours ago" % (comment_td.seconds / 3600)
        elif comment_td.days >= 1 and comment_td.days < 7:
            return "%s days ago" % comment_td.days
        elif comment_td.days >= 7 and comment_td.days < 30:
            return "%s weeks ago" % (comment_td.days / 7)
        elif comment_td.days >= 30 and comment_td.days < 365:
            return "%s months ago" % (comment_td.days / 30)
        else:
            return "%s years ago" % (comment_td.days / 365)

    def url(self):
        """The URL for the page for this comment"""
        return self.page.url() + '#comment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.page.title, self._id)

MappedClass.compile_all()
