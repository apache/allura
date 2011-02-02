from pylons import g #g is a namespace for globally accessable app helpers
from pylons import c as context

from ming import schema
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty

from allura.model import VersionedArtifact, Snapshot, Feed, Thread, Post, User, BaseAttachment
from allura.model import Notification, project_orm_session
from allura.lib import helpers as h
from allura.lib import patience
from allura.lib import utils

config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

class Globals(MappedClass):

    class __mongometa__:
        name = 'wiki-globals'
        session = project_orm_session
        indexes = [ 'app_config_id' ]

    type_s = 'WikiGlobals'
    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:context.app.config._id)
    root = FieldProperty(str)


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
    deleted=FieldProperty(bool, if_missing=False)
    type_s = 'Wiki'

    def commit(self):
        self.subscribe()
        VersionedArtifact.commit(self)
        if self.version > 1:
            v1 = self.get_version(self.version-1)
            v2 = self
            la = [ line + '\n'  for line in v1.text.splitlines() ]
            lb = [ line + '\n'  for line in v2.text.splitlines() ]
            diff = ''.join(patience.unified_diff(
                    la, lb,
                    'v%d' % v1.version,
                    'v%d' % v2.version))
            description = '<pre>' + diff + '</pre>'
            if v1.title != v2.title:
                subject = '%s renamed page %s to %s' % (
                    context.user.username, v2.title, v1.title)
            else:
                subject = '%s modified page %s' % (
                    context.user.username, self.title)
        else:
            description = self.text
            subject = '%s created page %s' % (
                context.user.username, self.title)
        Feed.post(self, description)
        Notification.post(
            artifact=self, topic='metadata', text=description, subject=subject)

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.title.replace('/', '.'), domain, config.common_suffix)

    @property
    def email_subject(self):
        return 'Discussion for %s page' % self.title

    def url(self):
        s = self.app_config.url() + h.urlquote(self.title.encode('utf-8')) + '/'
        if self.deleted:
            s += '?deleted=True'
        return s

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
        return WikiAttachment.query.find(dict(artifact_id=self._id, type='attachment'))

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
                           artifact_reference=obj.dump_ref())
            return obj
        else:
            pg = cls.upsert(title)
            HC = cls.__mongometa__.history_class
            ss = HC.query.find({'artifact_id':pg._id, 'version':int(version)}).one()
            return ss

    @classmethod
    def attachment_class(cls):
        return WikiAttachment

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

class WikiAttachment(BaseAttachment):
    ArtifactType=Page

MappedClass.compile_all()
