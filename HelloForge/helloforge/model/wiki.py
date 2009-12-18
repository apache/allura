from time import sleep

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

class Page(VersionedArtifact):
    class __mongometa__:
        name='page'
        history_class = PageHistory

    title=FieldProperty(str)
    text=FieldProperty(schema.String, if_missing='')

    def url(self):
        return self.app_config.script_name() + '/' + self.title + '/'

    def shorthand_id(self):
        return self.title

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title_s=self.title,
            version_i=self.version,
            type_s='WikiPage',
            text=self.text)
        return result
    
    @classmethod
    def upsert(cls, title, version=None):
        """Update page with `title` or insert new page with that name"""
        
        #If no version is specified
        if version is None:
            #Check for existing page object    
            obj = cls.query.get(
                app_config_id=context.app.config._id,
                title=title)
                
            #If there's no page, make one
            if obj is None:
                obj = cls(
                    title=title,
                    app_config_id=context.app.config._id,
                    )
            return obj
        else:
            #version was specified, move up from there and save...
            pg = cls.upsert(title)
            HC = cls.__mongometa__.history_class
            ss = HC.query.find({'artifact_id':pg._id, 'version':int(version)}).one()
            new_obj = dict(ss.data, version=version+1)
            return cls.make(new_obj)

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return to_html(self.text)

    def reply(self):
        while True:
            try:
                c = Comment.make(dict(page_id=self._id))
                c.query.insert()
                return c
            except OperationFailure:
                sleep(0.1)
                continue

    def root_comments(self):
        if '_id' in self:
            return Comment.query.find(dict(page_id=self._id, parent_id=None))
        else:
            return []

class Comment(Message):
    """Comment class, threaded, persisted in mongo on a per-page basis"""
    
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

    def url(self):
        """The URL for this specific comment"""
        return self.page.url() + '#comment-' + self._id

    def shorthand_id(self):
        return '%s-%s' % (self.page.title, self._id)

MappedClass.compile_all()
