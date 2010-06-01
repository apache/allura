from time import sleep
from datetime import datetime

import tg
from pylons import g #g is a namespace for globally accessable app helpers
from pylons import c as context

from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.base import state, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty

from pyforge.model import VersionedArtifact, Snapshot, Message, File, Feed, Thread, Post, User
from pyforge.model import Notification
from pyforge.lib import helpers as h

common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')

class PageHistory(Snapshot):
    class __mongometa__:
        name='page_history'

    def original(self):
        return Page.query.get(_id=self.artifact_id)

    def authors(self):
        return self.original().authors()
        
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
        return g.markdown_wiki.convert(self.data.text)

    @property
    def attachments(self):
        return self.original().attachments

    @property
    def email_address(self):
        return self.original().email_address

class Page(VersionedArtifact):
    class __mongometa__:
        name='page'
        history_class = PageHistory

    title=FieldProperty(str)
    text=FieldProperty(schema.String, if_missing='')
    viewable_by=FieldProperty([str])

    def commit(self):
        self.subscribe()
        VersionedArtifact.commit(self)
        if self.version > 1:
            t1 = self.upsert(self.title, self.version-1).text
            t2 = self.text
            description = h.diff_text(t1, t2)
            subject = 'Page %s modified' % self.title
        else:
            description = self.text
            subject = 'Page %s created' % self.title
        Feed.post(self, description)
        Notification.post(artifact=self, topic='metadata', text=description, subject=subject)

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.title.replace('/', '.'), domain, common_suffix)

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

    @property
    def attachments(self):
        return Attachment.by_metadata(page_id=self._id,type='attachment')

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
                t = Thread(discussion_id=obj.app_config.discussion_id,
                           artifact_reference=obj.dump_ref(),
                           subject='Discussion for %s page' % title)
            return obj
        else:
            pg = cls.upsert(title)
            HC = cls.__mongometa__.history_class
            ss = HC.query.find({'artifact_id':pg._id, 'version':int(version)}).one()
            return ss

    def reply(self, text):
        Feed.post(self, text)
        # Get thread
        thread = Thread.query.get(artifact_id=self._id)
        return Post(
            discussion_id=thread.discussion_id,
            thread_id=thread._id,
            text=text)

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return g.markdown_wiki.convert(self.text)

    def authors(self):
        """All the users that have edited this page"""
        def uniq(users):
            t = {}
            for user in users:
                t[user.username] = user.id
            return t.values()
        user_ids = uniq([r.author for r in self.history().all()])
        return User.query.find({'_id':{'$in':user_ids}}).all()

class Attachment(File):
    class __mongometa__:
        name = 'attachment.files'
        indexes = [
            'metadata.filename',
            'metadata.page_id' ]

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            page_id=schema.ObjectId,
            app_config_id=schema.ObjectId,
            type=str,
            filename=str))

    @property
    def page(self):
        return Page.query.get(_id=self.metadata.page_id)

    def url(self):
        return self.page.url() + 'attachment/' + self.filename


MappedClass.compile_all()
