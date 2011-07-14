from datetime import datetime
from random import randint

from pylons import c, g
from pymongo.errors import DuplicateKeyError

from ming import schema
from ming.orm import FieldProperty, Mapper, session, state
from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils, patience, htmltruncate

config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

class BlogPostSnapshot(M.Snapshot):
    class __mongometa__:
        name='blog_post_snapshot'
    type_s='Blog Post Snapshot'

    def original(self):
        return BlogPost.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = super(BlogPostSnapshot, self).index()
        result.update(
            title_s='Version %d of %s' % (
                self.version, self.original().shorthand_id()),
            type_s=self.type_s,
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

class BlogPost(M.VersionedArtifact):
    class __mongometa__:
        name='blog_post'
        history_class = BlogPostSnapshot
        unique_indexes = [ ('project_id', 'app_config_id', 'slug') ]
    type_s = 'Blog Post'

    title = FieldProperty(str, if_missing='Untitled')
    text = FieldProperty(str, if_missing='')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    slug = FieldProperty(str)
    state = FieldProperty(schema.OneOf('draft', 'published'), if_missing='draft')

    def author(self):
        '''The author of the first snapshot of this BlogPost'''
        return M.User.query.get(_id=self.get_version(1).author.id) or M.User.anonymous()

    def _get_date(self):
        return self.timestamp.date()
    def _set_date(self, value):
        self.timestamp = datetime.combine(value, self.time)
    date = property(_get_date, _set_date)

    def _get_time(self):
        return self.timestamp.time()
    def _set_time(self, value):
        self.timestamp = datetime.combine(self.date, value)
    time = property(_get_time, _set_time)

    @property
    def html_text(self):
        return g.markdown.convert(self.text)

    @property
    def html_text_preview(self):
        indicator = '... [read more](%s)' % self.url()
        return g.markdown.convert(htmltruncate.truncate(self.text, 200, ellipsis=indicator))

    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.title.replace('/', '.'), domain, config.common_suffix)

    def make_slug(self):
        slugsafe = ''.join(
            ch.lower()
            for ch in self.title.replace(' ', '-')
            if ch.isalnum() or ch == '-')
        base = '%s/%s' % (
            self.timestamp.strftime('%Y/%m'),
            slugsafe)
        self.slug = base
        while True:
            try:
                session(self).insert_now(self, state(self))
                return self.slug
            except DuplicateKeyError:
                self.slug = base + '-%.3d' % randint(0,999)
                return self.slug

    def url(self):
        return self.app.url + self.slug + '/'

    def shorthand_id(self):
        return self.slug

    def index(self):
        result = super(BlogPost, self).index()
        result.update(
            title_s=self.slug,
            type_s=self.type_s,
            state_s=self.state,
            snippet_s='%s: %s' % (self.title, h.text.truncate(self.text, 200)),
            text=self.text)
        return result

    def get_version(self, version):
        HC = self.__mongometa__.history_class
        return HC.query.find({'artifact_id':self._id, 'version':int(version)}).one()

    def commit(self):
        self.subscribe()
        super(BlogPost, self).commit()
        if self.version > 1:
            v1 = self.get_version(self.version-1)
            v2 = self
            la = [ line + '\n'  for line in v1.text.splitlines() ]
            lb = [ line + '\n'  for line in v2.text.splitlines() ]
            diff = ''.join(patience.unified_diff(
                    la, lb,
                    'v%d' % v1.version,
                    'v%d' % v2.version))
            description = diff
            if v1.state != 'published' and v2.state == 'published':
                M.Feed.post(self, self.title, self.text, author=self.author())
                description = self.text
                subject = '%s created post %s' % (
                    c.user.username, self.title)
            elif v1.title != v2.title:
                subject = '%s renamed post %s to %s' % (
                    c.user.username, v2.title, v1.title)
            else:
                subject = '%s modified post %s' % (
                    c.user.username, self.title)
        else:
            description = self.text
            subject = '%s created post %s' % (
                c.user.username, self.title)
            if self.state == 'published':
                M.Feed.post(self, self.title, self.text, author=self.author())
        if self.state == 'published':
            M.Notification.post(
                artifact=self, topic='metadata', text=description, subject=subject)

class Attachment(M.BaseAttachment):
    ArtifactClass=BlogPost
    class __mongometa__:
        polymorphic_identity='BlogAttachment'
    attachment_type=FieldProperty(str, if_missing='BlogAttachment')


Mapper.compile_all()
