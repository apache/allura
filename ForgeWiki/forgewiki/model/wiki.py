#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from datetime import datetime
import difflib
import os
import typing

# g is a namespace for globally accessable app helpers
from tg import app_globals as g
from tg import tmpl_context as context

from ming import schema
from ming.orm import FieldProperty, ForeignIdProperty, Mapper, session
from ming.orm.declarative import MappedClass

from tg import config as tg_config

from allura.model import (
    VersionedArtifact,
    Snapshot,
    Feed,
    Thread,
    Post,
    User,
    BaseAttachment,
    Notification,
    project_orm_session,
    Shortlink,
)
from allura.model.timeline import ActivityObject
from allura.model.types import MarkdownCache

from allura.lib import helpers as h
from allura.lib import utils

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


config = utils.ConfigProxy(
    common_suffix='forgemail.domain')


class Globals(MappedClass):

    class __mongometa__:
        name = 'wiki-globals'
        session = project_orm_session
        indexes = ['app_config_id']

    query: 'Query[Globals]'

    type_s = 'WikiGlobals'

    _id = FieldProperty(schema.ObjectId)
    app_config_id = ForeignIdProperty(
        'AppConfig', if_missing=lambda: context.app.config._id)
    root = FieldProperty(str)


class PageHistory(Snapshot):

    class __mongometa__:
        name = 'page_history'

    query: 'Query[PageHistory]'

    def original(self):
        return Page.query.get(_id=self.artifact_id)

    def authors(self):
        return self.original().authors()

    def shorthand_id(self):
        return f'{self.original().shorthand_id()}#{self.version}'

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = Snapshot.index(self)
        title = '%s (version %d)' % (self.original().title, self.version)
        result.update(
            title=title,
            type_s='WikiPage Snapshot',
            text=self.data.text)
        return result

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return g.markdown_wiki.convert(self.data.text)

    @property
    def email_address(self):
        return self.original().email_address


class Page(VersionedArtifact, ActivityObject):

    class __mongometa__:
        name = 'page'
        history_class = PageHistory
        unique_indexes = [('app_config_id', 'title')]

    query: 'Query[Page]'

    title = FieldProperty(str)
    text = FieldProperty(schema.String, if_missing='')
    text_cache = FieldProperty(MarkdownCache)
    viewable_by = FieldProperty(schema.Deprecated)
    type_s = 'Wiki'

    @property
    def activity_name(self):
        return 'a wiki page'

    @property
    def type_name(self):
        return 'wiki page'

    @property
    def activity_extras(self):
        d = ActivityObject.activity_extras.fget(self)
        d.update(summary=self.title)
        return d

    def attachments_for_export(self):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url()),
                     path=os.path.join(
                         self.app_config.options.mount_point,
                         str(self._id),
                         os.path.basename(attach.filename))) for attach in self.attachments]

    def attachments_for_json(self):
        return [dict(bytes=attach.length,
                     url=h.absurl(attach.url())) for attach in self.attachments]

    def __json__(self, posts_limit=None, is_export=False):
        return dict(super().__json__(posts_limit=posts_limit, is_export=is_export),
                    title=self.title,
                    text=self.text,
                    labels=list(self.labels),
                    attachments=self.attachments_for_export() if is_export else self.attachments_for_json())

    def commit(self, subscribe=False):
        if subscribe:
            self.subscribe()
        ss = VersionedArtifact.commit(self)
        session(self).flush()
        if self.version > 1:
            v1 = self.get_version(self.version - 1)
            v2 = self
            la = [line + '\n' for line in v1.text.splitlines()]
            lb = [line + '\n' for line in v2.text.splitlines()]
            diff = ''.join(difflib.unified_diff(
                la, lb,
                'v%d' % v1.version,
                'v%d' % v2.version))
            description = '<pre>' + diff + '</pre>'
            if v1.title != v2.title:
                subject = '{} renamed page {} to {}'.format(
                    context.user.username, v1.title, v2.title)
            else:
                subject = '{} modified page {}'.format(
                    context.user.username, self.title)
        else:
            description = self.text
            subject = '{} created page {}'.format(
                context.user.username, self.title)
        Feed.post(self, title=None, description=description)
        Notification.post(
            artifact=self, topic='metadata', text=description, subject=subject)
        return ss

    @property
    def email_address(self):
        if context.app.config.options.get('AllowEmailPosting', True):
            domain = self.email_domain
            title = self.title.replace(' ', '_')
            return '{}@{}{}'.format(title.replace('/', '.'), domain, config.common_suffix)
        else:
            return tg_config.get('forgemail.return_path')

    @property
    def email_subject(self):
        return 'Discussion for %s page' % self.title

    def url(self):
        s = self.app_config.url() + h.urlquote(self.title) + '/'
        if self.deleted:
            s += '?deleted=True'
        return s

    def shorthand_id(self):
        return self.title

    def index(self):
        result = VersionedArtifact.index(self)
        result.update(
            title=self.title,
            version_i=self.version,
            type_s='WikiPage',
            text=self.text)
        return result

    @classmethod
    def upsert(cls, title, version=None):
        """Update page with `title` or insert new page with that name"""
        if version is None:
            # Check for existing page object
            obj = cls.query.get(
                app_config_id=context.app.config._id,
                title=title)
            if obj is None:
                obj = cls(
                    title=title,
                    app_config_id=context.app.config._id,
                )
                Thread.new(discussion_id=obj.app_config.discussion_id,
                           ref_id=obj.index_id())
            return obj
        else:
            pg = cls.upsert(title)
            HC = cls.__mongometa__.history_class
            ss = HC.query.find(
                {'artifact_id': pg._id, 'version': int(version)}).one()
            return ss

    @classmethod
    def find_page(cls, title):
        """Find page with `title`"""
        # Check for existing page object
        obj = cls.query.get(
            app_config_id=context.app.config._id,
            title=title)
        return obj

    @classmethod
    def attachment_class(cls):
        return WikiAttachment

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return g.markdown_wiki.cached_convert(self, 'text')

    def authors(self):
        """All the users that have edited this page"""
        def uniq(users):
            t = {}
            for user in users:
                t[user.username] = user.id
            return list(t.values())
        user_ids = uniq([r.author for r in self.history().all()])
        return User.query.find({
            '_id': {'$in': user_ids},
            'disabled': False,
            'pending': False
        }).all()

    def delete(self):
        subject = '{} removed page {}'.format(
            context.user.username, self.title)
        description = self.text
        Notification.post(
            artifact=self, topic='metadata', text=description, subject=subject)
        Shortlink.query.remove(dict(ref_id=self.index_id()))
        self.deleted = True
        suffix = f" {datetime.utcnow():%Y-%m-%d %H:%M:%S.%f}"
        self.title += suffix


class WikiAttachment(BaseAttachment):
    ArtifactType = Page
    thumbnail_size = (100, 100)

    class __mongometa__:
        polymorphic_identity = 'WikiAttachment'

    query: 'Query[WikiAttachment]'

    attachment_type = FieldProperty(str, if_missing='WikiAttachment')

Mapper.compile_all()
