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

import logging
from collections import defaultdict
from datetime import datetime

import pymongo
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from ming import schema as S
from ming.orm import state, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.declarative import MappedClass
from ming.utils import LazyProperty
from webhelpers import feedgenerator as FG

from allura.lib import helpers as h
from allura.lib import security
from .session import main_orm_session
from .session import project_orm_session
from .session import artifact_orm_session
from .index import ArtifactReference
from .types import ACL, MarkdownCache
from .project import AppConfig
from .notification import MailFooter

from filesystem import File

log = logging.getLogger(__name__)


class Artifact(MappedClass):

    """
    Base class for anything you want to keep track of.

    - Automatically indexed into Solr (see index() method)
    - Has a discussion thread that can have files attached to it

    :var mod_date: last-modified :class:`datetime`
    :var acl: dict of permission name => [roles]
    :var labels: list of plain old strings

    """
    class __mongometa__:
        session = artifact_orm_session
        name = 'artifact'
        indexes = [
            ('app_config_id', 'labels'),
        ]

        def before_save(data):
            _session = artifact_orm_session._get()
            skip_mod_date = getattr(_session, 'skip_mod_date', False)
            skip_last_updated = getattr(_session, 'skip_last_updated', False)
            if not skip_mod_date:
                data['mod_date'] = datetime.utcnow()
            else:
                log.debug('Not updating mod_date')
            if c.project and not skip_last_updated:
                c.project.last_updated = datetime.utcnow()
    type_s = 'Generic Artifact'

    # Artifact base schema
    _id = FieldProperty(S.ObjectId)
    mod_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    app_config_id = ForeignIdProperty(
        'AppConfig', if_missing=lambda: c.app.config._id)
    plugin_verson = FieldProperty(S.Deprecated)
    tool_version = FieldProperty(S.Deprecated)
    acl = FieldProperty(ACL)
    tags = FieldProperty(S.Deprecated)
    labels = FieldProperty([str])
    references = FieldProperty(S.Deprecated)
    backreferences = FieldProperty(S.Deprecated)
    app_config = RelationProperty('AppConfig')
    # Not null if artifact originated from external import.  The import ID is
    # implementation specific, but should probably be an object indicating
    # the source, original ID, and any other info needed to identify where
    # the artifact came from.  But if you only have one source, a str might do.
    import_id = FieldProperty(None, if_missing=None)
    deleted = FieldProperty(bool, if_missing=False)

    def __json__(self):
        """Return a JSON-encodable :class:`dict` representation of this
        Artifact.

        """
        return dict(
            _id=str(self._id),
            mod_date=self.mod_date,
            labels=list(self.labels),
            related_artifacts=[a.url() for a in self.related_artifacts()],
            discussion_thread=self.discussion_thread.__json__(),
            discussion_thread_url=h.absurl('/rest%s' %
                                           self.discussion_thread.url()),
        )

    def parent_security_context(self):
        """Return the :class:`allura.model.project.AppConfig` instance for
        this Artifact.

        ACL processing for this Artifact continues at the AppConfig object.
        This lets AppConfigs provide a 'default' ACL for all artifacts in the
        tool.

        """
        return self.app_config

    @classmethod
    def attachment_class(cls):
        raise NotImplementedError, 'attachment_class'

    @classmethod
    def translate_query(cls, q, fields):
        """Return a translated Solr query (``q``), where generic field
        identifiers are replaced by the 'strongly typed' versions defined in
        ``fields``.

        """
        for f in fields:
            if '_' in f:
                base, typ = f.rsplit('_', 1)
                q = q.replace(base + ':', f + ':')
        return q

    @LazyProperty
    def ref(self):
        """Return :class:`allura.model.index.ArtifactReference` for this
        Artifact.

        """
        return ArtifactReference.from_artifact(self)

    @LazyProperty
    def refs(self):
        """Artifacts referenced by this one.

        :return: list of :class:`allura.model.index.ArtifactReference`
        """
        return self.ref.references

    @LazyProperty
    def backrefs(self):
        """Artifacts that reference this one.

        :return: list of :attr:`allura.model.index.ArtifactReference._id`'s

        """
        q = ArtifactReference.query.find(dict(references=self.index_id()))
        return [aref._id for aref in q]

    def related_artifacts(self):
        """Return all Artifacts that are related to this one.

        """
        related_artifacts = []
        for ref_id in self.refs + self.backrefs:
            ref = ArtifactReference.query.get(_id=ref_id)
            if ref is None:
                continue
            artifact = ref.artifact
            if artifact is None:
                continue
            artifact = artifact.primary()
            if artifact is None:
                continue
            # don't link to artifacts in deleted tools
            if hasattr(artifact, 'app_config') and artifact.app_config is None:
                continue
            # TODO: This should be refactored. We shouldn't be checking
            # artifact type strings in platform code.
            if artifact.type_s == 'Commit' and not artifact.repo:
                ac = AppConfig.query.get(
                    _id=ref.artifact_reference['app_config_id'])
                app = ac.project.app_instance(ac) if ac else None
                if app:
                    artifact.set_context(app.repo)
            if artifact not in related_artifacts and (getattr(artifact, 'deleted', False) == False):
                related_artifacts.append(artifact)
        return sorted(related_artifacts, key=lambda a: a.url())

    def subscribe(self, user=None, topic=None, type='direct', n=1, unit='day'):
        """Subscribe ``user`` to the :class:`allura.model.notification.Mailbox`
        for this Artifact.

        :param user: :class:`allura.model.auth.User`

        If ``user`` is None, ``c.user`` will be subscribed.

        """
        from allura.model import Mailbox
        if user is None:
            user = c.user
        Mailbox.subscribe(
            user_id=user._id,
            project_id=self.app_config.project_id,
            app_config_id=self.app_config._id,
            artifact=self, topic=topic,
            type=type, n=n, unit=unit)

    def unsubscribe(self, user=None):
        """Unsubscribe ``user`` from the
        :class:`allura.model.notification.Mailbox` for this Artifact.

        :param user: :class:`allura.model.auth.User`

        If ``user`` is None, ``c.user`` will be unsubscribed.

        """
        from allura.model import Mailbox
        if user is None:
            user = c.user
        Mailbox.unsubscribe(
            user_id=user._id,
            project_id=self.app_config.project_id,
            app_config_id=self.app_config._id,
            artifact_index_id=self.index_id())

    def primary(self):
        """If an artifact is a "secondary" artifact (discussion of a ticket, for
        instance), return the artifact that is the "primary".

        """
        return self

    @classmethod
    def artifacts_labeled_with(cls, label, app_config):
        """Return all artifacts of type ``cls`` that have the label ``label`` and
        are in the tool denoted by ``app_config``.

        :param label: str
        :param app_config: :class:`allura.model.project.AppConfig` instance

        """
        return cls.query.find({'labels': label, 'app_config_id': app_config._id})

    def email_link(self, subject='artifact'):
        """Return a 'mailto' URL for this Artifact, with optional subject.

        """
        if subject:
            return 'mailto:%s?subject=[%s:%s:%s] Re: %s' % (
                self.email_address,
                self.app_config.project.shortname,
                self.app_config.options.mount_point,
                self.shorthand_id(),
                subject)
        else:
            return 'mailto:%s' % self.email_address

    @property
    def project(self):
        """Return the :class:`allura.model.project.Project` instance to which
        this Artifact belongs.

        """
        return getattr(self.app_config, 'project', None)

    @property
    def project_id(self):
        """Return the ``_id`` of the :class:`allura.model.project.Project`
        instance to which this Artifact belongs.

        """
        return self.app_config.project_id

    @LazyProperty
    def app(self):
        """Return the :class:`allura.model.app.Application` instance to which
        this Artifact belongs.

        """
        if not self.app_config:
            return None
        if getattr(c, 'app', None) and c.app.config._id == self.app_config._id:
            return c.app
        else:
            return self.app_config.load()(self.project, self.app_config)

    def index_id(self):
        """Return a globally unique artifact identifier.

        Used for SOLR ID, shortlinks, and possibly elsewhere.

        """
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    def index(self):
        """Return a :class:`dict` representation of this Artifact suitable for
        search indexing.

        Subclasses should override this, providing a dictionary of solr_field => value.
        These fields & values will be stored by Solr.  Subclasses should call the
        super() index() and then extend it with more fields.

        You probably want to override at least title and text to have
        meaningful search results and email senders.

        You can take advantage of Solr's dynamic field typing by adding a type
        suffix to your field names, e.g.:

            _s (string) (not analyzed)
            _t (text) (analyzed)
            _b (bool)
            _i (int)

        """
        project = self.project
        return dict(
            id=self.index_id(),
            mod_date_dt=self.mod_date,
            title='Artifact %s' % self._id,
            project_id_s=str(project._id),
            project_name_t=project.name,
            project_shortname_t=project.shortname,
            tool_name_s=self.app_config.tool_name,
            mount_point_s=self.app_config.options.mount_point,
            is_history_b=False,
            url_s=self.url(),
            type_s=self.type_s,
            labels_t=' '.join(l for l in self.labels),
            snippet_s='',
            deleted_b=self.deleted)

    def url(self):
        """Return the URL for this Artifact.

        Subclasses must implement this.

        """
        raise NotImplementedError, 'url'  # pragma no cover

    def shorthand_id(self):
        """How to refer to this artifact within the app instance context.

        For a wiki page, it might be the title.  For a ticket, it might be the
        ticket number.  For a discussion, it might be the message ID.  Generally
        this should have a strong correlation to the URL.

        """
        return str(self._id)  # pragma no cover

    def link_text(self):
        """Return the link text to use when a shortlink to this artifact
        is expanded into an <a></a> tag.

        By default this method returns :attr:`type_s` + :meth:`shorthand_id`. Subclasses should
        override this method to provide more descriptive link text.

        """
        return self.shorthand_id()

    def get_discussion_thread(self, data=None):
        """Return the discussion thread and parent_id for this artifact.

        :return: (:class:`allura.model.discuss.Thread`, parent_thread_id (int))

        """
        from .discuss import Thread
        t = Thread.query.get(ref_id=self.index_id())
        if t is None:
            idx = self.index()
            t = Thread.new(
                app_config_id=self.app_config_id,
                discussion_id=self.app_config.discussion_id,
                ref_id=idx['id'],
                subject='%s discussion' % h.get_first(idx, 'title'))
        parent_id = None
        if data:
            in_reply_to = data.get('in_reply_to', [])
            if in_reply_to:
                parent_id = in_reply_to[0]
        return t, parent_id

    @LazyProperty
    def discussion_thread(self):
        """Return the :class:`discussion thread <allura.model.discuss.Thread>`
        for this Artifact.

        """
        return self.get_discussion_thread()[0]

    def add_multiple_attachments(self, file_info):
        if not isinstance(file_info, list):
            file_info = [file_info]
        for attach in file_info:
            if hasattr(attach, 'file'):
                self.attach(attach.filename, attach.file,
                            content_type=attach.type)

    def attach(self, filename, fp, **kw):
        """Attach a file to this Artifact.

        :param filename: file name
        :param fp: a file-like object (implements ``read()``)
        :param \*\*kw: passed through to Attachment class constructor

        """
        att = self.attachment_class().save_attachment(
            filename=filename,
            fp=fp, artifact_id=self._id, **kw)
        return att

    @LazyProperty
    def attachments(self):
        return self.attachment_class().query.find(dict(
            app_config_id=self.app_config_id, artifact_id=self._id, type='attachment')).all()

    def delete(self):
        """Delete this Artifact.

        """
        ArtifactReference.query.remove(dict(_id=self.index_id()))
        super(Artifact, self).delete()

    def get_mail_footer(self, notification, toaddr):
        return MailFooter.standard(notification)

    def message_id(self):
        '''Persistent, email-friendly (Message-ID header) id of this artifact'''
        return h.gen_message_id(self._id)


class Snapshot(Artifact):

    """A snapshot of an :class:`Artifact <allura.model.artifact.Artifact>`, used in :class:`VersionedArtifact <allura.model.artifact.VersionedArtifact>`"""
    class __mongometa__:
        session = artifact_orm_session
        name = 'artifact_snapshot'
        unique_indexes = [('artifact_class', 'artifact_id', 'version')]
        indexes = [('artifact_id', 'version')]

    _id = FieldProperty(S.ObjectId)
    artifact_id = FieldProperty(S.ObjectId)
    artifact_class = FieldProperty(str)
    version = FieldProperty(S.Int, if_missing=0)
    author = FieldProperty(dict(
        id=S.ObjectId,
        username=str,
        display_name=str,
        logged_ip=str))
    timestamp = FieldProperty(datetime)
    data = FieldProperty(None)

    def index(self):
        result = Artifact.index(self)
        original = self.original()
        if original:
            original_index = original.index()
            result.update(original_index)
            result['title'] = '%s (version %d)' % (
                h.get_first(original_index, 'title'), self.version)
        result.update(
            id=self.index_id(),
            version_i=self.version,
            author_username_t=self.author.username,
            author_display_name_t=self.author.display_name,
            timestamp_dt=self.timestamp,
            is_history_b=True)
        return result

    def original(self):
        raise NotImplemented, 'original'  # pragma no cover

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    @property
    def attachments(self):
        orig = self.original()
        if not orig:
            return None
        return orig.attachments

    def __getattr__(self, name):
        return getattr(self.data, name)


class VersionedArtifact(Artifact):

    """
    An :class:`Artifact <allura.model.artifact.Artifact>` that has versions.
    Associated data like attachments and discussion thread are not versioned.
    """
    class __mongometa__:
        session = artifact_orm_session
        name = 'versioned_artifact'
        history_class = Snapshot

    version = FieldProperty(S.Int, if_missing=0)

    def commit(self, update_stats=True):
        '''Save off a snapshot of the artifact and increment the version #'''
        self.version += 1
        try:
            ip_address = request.headers.get(
                'X_FORWARDED_FOR', request.remote_addr)
            ip_address = ip_address.split(',')[0].strip()
        except:
            ip_address = '0.0.0.0'
        data = dict(
            artifact_id=self._id,
            artifact_class='%s.%s' % (
                self.__class__.__module__,
                self.__class__.__name__),
            version=self.version,
            author=dict(
                id=c.user._id,
                username=c.user.username,
                display_name=c.user.get_pref('display_name'),
                logged_ip=ip_address),
            timestamp=datetime.utcnow(),
            data=state(self).clone())
        ss = self.__mongometa__.history_class(**data)
        session(ss).insert_now(ss, state(ss))
        log.info('Snapshot version %s of %s',
                 self.version, self.__class__)
        if update_stats:
            if self.version > 1:
                g.statsUpdater.modifiedArtifact(
                    self.type_s, self.mod_date, self.project, c.user)
            else:
                g.statsUpdater.newArtifact(
                    self.type_s, self.mod_date, self.project, c.user)
        return ss

    def get_version(self, n):
        if n < 0:
            n = self.version + n + 1
        ss = self.__mongometa__.history_class.query.get(
            artifact_id=self._id,
            artifact_class='%s.%s' % (
                self.__class__.__module__,
                self.__class__.__name__),
            version=n)
        if ss is None:
            raise IndexError, n
        return ss

    def revert(self, version):
        ss = self.get_version(version)
        old_version = self.version
        for k, v in ss.data.iteritems():
            setattr(self, k, v)
        self.version = old_version

    def history(self):
        HC = self.__mongometa__.history_class
        q = HC.query.find(dict(artifact_id=self._id)).sort(
            'version', pymongo.DESCENDING)
        return q

    @property
    def last_updated(self):
        history = self.history()
        if history.count():
            return self.history().first().timestamp
        else:
            return self.mod_date

    def delete(self):
        # remove history so that the snapshots aren't left orphaned
        super(VersionedArtifact, self).delete()
        HC = self.__mongometa__.history_class
        HC.query.remove(dict(artifact_id=self._id))


class Message(Artifact):

    """
    A message

    :var _id: an email friendly (e.g. message-id) string id
    :var slug: slash-delimeted random identifier.  Slashes useful for threaded searching and ordering
    :var full_slug: string of slash-delimited "timestamp:slug" components.  Useful for sorting by timstamp
    """

    class __mongometa__:
        session = artifact_orm_session
        name = 'message'
    type_s = 'Generic Message'

    _id = FieldProperty(str, if_missing=h.gen_message_id)
    slug = FieldProperty(str, if_missing=h.nonce)
    full_slug = FieldProperty(str, if_missing=None)
    parent_id = FieldProperty(str)
    app_id = FieldProperty(S.ObjectId, if_missing=lambda: c.app.config._id)
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id = FieldProperty(S.ObjectId, if_missing=lambda: c.user._id)
    text = FieldProperty(str, if_missing='')

    @classmethod
    def make_slugs(cls, parent=None, timestamp=None):
        part = h.nonce()
        if timestamp is None:
            timestamp = datetime.utcnow()
        dt = timestamp.strftime('%Y%m%d%H%M%S')
        slug = part
        full_slug = dt + ':' + part
        if parent:
            return (parent.slug + '/' + slug,
                    parent.full_slug + '/' + full_slug)
        else:
            return slug, full_slug

    def author(self):
        from .auth import User
        return User.query.get(_id=self.author_id) or User.anonymous()

    def index(self):
        result = Artifact.index(self)
        author = self.author()
        result.update(
            author_user_name_t=author.username,
            author_display_name_t=author.get_pref('display_name'),
            timestamp_dt=self.timestamp,
            text=self.text)
        return result

    def shorthand_id(self):
        return self.slug


class AwardFile(File):

    class __mongometa__:
        session = main_orm_session
        name = 'award_file'
    award_id = FieldProperty(S.ObjectId)


class Award(Artifact):

    class __mongometa__:
        session = main_orm_session
        name = 'award'
        indexes = ['short']
    type_s = 'Generic Award'

    from .project import Neighborhood
    _id = FieldProperty(S.ObjectId)
    created_by_neighborhood_id = ForeignIdProperty(
        Neighborhood, if_missing=None)
    created_by_neighborhood = RelationProperty(
        Neighborhood, via='created_by_neighborhood_id')
    short = FieldProperty(str, if_missing=h.nonce)
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    full = FieldProperty(str, if_missing='')

    def index(self):
        result = Artifact.index(self)
        result.update(
            _id_s=self._id,
            short_s=self.short,
            timestamp_dt=self.timestamp,
            full_s=self.full)
        if self.created_by:
            result['created_by_s'] = self.created_by.name
        return result

    @property
    def icon(self):
        return AwardFile.query.get(award_id=self._id)

    def url(self):
        return str(self._id)

    def longurl(self):
        return self.created_by_neighborhood.url_prefix + "_admin/awards/" + self.url()

    def shorthand_id(self):
        return self.short


class AwardGrant(Artifact):

    "An :class:`Award <allura.model.artifact.Award>` can be bestowed upon a project by a neighborhood"
    class __mongometa__:
        session = main_orm_session
        name = 'grant'
        indexes = ['short']
    type_s = 'Generic Award Grant'

    _id = FieldProperty(S.ObjectId)
    award_id = ForeignIdProperty(Award, if_missing=None)
    award = RelationProperty(Award, via='award_id')
    granted_by_neighborhood_id = ForeignIdProperty(
        'Neighborhood', if_missing=None)
    granted_by_neighborhood = RelationProperty(
        'Neighborhood', via='granted_by_neighborhood_id')
    granted_to_project_id = ForeignIdProperty('Project', if_missing=None)
    granted_to_project = RelationProperty(
        'Project', via='granted_to_project_id')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)

    def index(self):
        result = Artifact.index(self)
        result.update(
            _id_s=self._id,
            short_s=self.short,
            timestamp_dt=self.timestamp,
            full_s=self.full)
        if self.award:
            result['award_s'] = self.award.short
        return result

    @property
    def icon(self):
        return AwardFile.query.get(award_id=self.award_id)

    def url(self):
        slug = str(self.granted_to_project.shortname).replace('/', '_')
        return h.urlquote(slug)

    def longurl(self):
        slug = str(self.granted_to_project.shortname).replace('/', '_')
        slug = self.award.longurl() + '/' + slug
        return h.urlquote(slug)

    def shorthand_id(self):
        if self.award:
            return self.award.short
        else:
            return None


class Feed(MappedClass):

    """
    Used to generate rss/atom feeds.  This does not need to be extended;
    all feed items go into the same collection
    """
    class __mongometa__:
        session = project_orm_session
        name = 'artifact_feed'
        indexes = [
            'pubdate',
            ('artifact_ref.project_id', 'artifact_ref.mount_point'),
            (('ref_id', pymongo.ASCENDING),
             ('pubdate', pymongo.DESCENDING)),
            (('project_id', pymongo.ASCENDING),
             ('app_config_id', pymongo.ASCENDING),
             ('pubdate', pymongo.DESCENDING)),
            # used in ext/user_profile/user_main.py for user feeds
            'author_link',
            # used in project feed
            (('project_id', pymongo.ASCENDING),
             ('pubdate', pymongo.DESCENDING)),
        ]

    _id = FieldProperty(S.ObjectId)
    ref_id = ForeignIdProperty('ArtifactReference')
    neighborhood_id = ForeignIdProperty('Neighborhood')
    project_id = ForeignIdProperty('Project')
    app_config_id = ForeignIdProperty('AppConfig')
    tool_name = FieldProperty(str)
    title = FieldProperty(str)
    link = FieldProperty(str)
    pubdate = FieldProperty(datetime, if_missing=datetime.utcnow)
    description = FieldProperty(str)
    description_cache = FieldProperty(MarkdownCache)
    unique_id = FieldProperty(str, if_missing=lambda: h.nonce(40))
    author_name = FieldProperty(str, if_missing=lambda: c.user.get_pref(
        'display_name') if hasattr(c, 'user') else None)
    author_link = FieldProperty(
        str, if_missing=lambda: c.user.url() if hasattr(c, 'user') else None)
    artifact_reference = FieldProperty(S.Deprecated)

    @classmethod
    def post(cls, artifact, title=None, description=None, author=None, author_link=None, author_name=None, pubdate=None, link=None, **kw):
        """
        Create a Feed item.  Returns the item.
        But if anon doesn't have read access, create does not happen and None is returned
        """
        # TODO: fix security system so we can do this correctly and fast
        from allura import model as M
        anon = M.User.anonymous()
        if not security.has_access(artifact, 'read', user=anon):
            return
        if not security.has_access(c.project, 'read', user=anon):
            return
        idx = artifact.index()
        if author is None:
            author = c.user
        if author_name is None:
            author_name = author.get_pref('display_name')
        if title is None:
            title = '%s modified by %s' % (
                h.get_first(idx, 'title'), author_name)
        if description is None:
            description = title
        if pubdate is None:
            pubdate = datetime.utcnow()
        if link is None:
            link = artifact.url()
        item = cls(
            ref_id=artifact.index_id(),
            neighborhood_id=artifact.app_config.project.neighborhood_id,
            project_id=artifact.app_config.project_id,
            app_config_id=artifact.app_config_id,
            tool_name=artifact.app_config.tool_name,
            title=title,
            description=g.markdown.convert(description),
            link=link,
            pubdate=pubdate,
            author_name=author_name,
            author_link=author_link or author.url())
        unique_id = kw.pop('unique_id', None)
        if unique_id:
            item.unique_id = unique_id
        return item

    @classmethod
    def feed(cls, q, feed_type, title, link, description,
             since=None, until=None, offset=None, limit=None):
        "Produces webhelper.feedgenerator Feed"
        d = dict(title=title, link=h.absurl(link),
                 description=description, language=u'en')
        if feed_type == 'atom':
            feed = FG.Atom1Feed(**d)
        elif feed_type == 'rss':
            feed = FG.Rss201rev2Feed(**d)
        query = defaultdict(dict)
        query.update(q)
        if since is not None:
            query['pubdate']['$gte'] = since
        if until is not None:
            query['pubdate']['$lte'] = until
        cur = cls.query.find(query)
        cur = cur.sort('pubdate', pymongo.DESCENDING)
        if limit is None:
            limit = 10
        query = cur.limit(limit)
        if offset is not None:
            query = cur.offset(offset)
        for r in cur:
            feed.add_item(title=r.title,
                          link=h.absurl(r.link.encode('utf-8')),
                          pubdate=r.pubdate,
                          description=r.description,
                          unique_id=h.absurl(r.unique_id),
                          author_name=r.author_name,
                          author_link=h.absurl(r.author_link))
        return feed


class VotableArtifact(MappedClass):

    """Voting support for the Artifact. Use as a mixin."""

    class __mongometa__:
        session = main_orm_session
        name = 'vote'

    votes = FieldProperty(int, if_missing=0)
    votes_up = FieldProperty(int, if_missing=0)
    votes_down = FieldProperty(int, if_missing=0)
    votes_up_users = FieldProperty([str], if_missing=list())
    votes_down_users = FieldProperty([str], if_missing=list())

    def vote_up(self, user):
        voted = self.user_voted(user)
        if voted == 1:
            # Already voted up - unvote
            self.votes_up_users.remove(user.username)
            self.votes_up -= 1
        elif voted == -1:
            # Change vote to negative
            self.votes_down_users.remove(user.username)
            self.votes_down -= 1
            self.votes_up_users.append(user.username)
            self.votes_up += 1
        else:
            self.votes_up_users.append(user.username)
            self.votes_up += 1
        self.votes = self.votes_up - self.votes_down

    def vote_down(self, user):
        voted = self.user_voted(user)
        if voted == -1:
            # Already voted down - unvote
            self.votes_down_users.remove(user.username)
            self.votes_down -= 1
        elif voted == 1:
            # Change vote to positive
            self.votes_up_users.remove(user.username)
            self.votes_up -= 1
            self.votes_down_users.append(user.username)
            self.votes_down += 1
        else:
            self.votes_down_users.append(user.username)
            self.votes_down += 1
        self.votes = self.votes_up - self.votes_down

    def user_voted(self, user):
        """Check that user voted for this artifact.

        Return:
        1 if user voted up
        -1 if user voted down
        0 if user doesn't vote
        """
        if user.username in self.votes_up_users:
            return 1
        if user.username in self.votes_down_users:
            return -1
        return 0

    @property
    def votes_up_percent(self):
        votes_count = self.votes_up + self.votes_down
        if votes_count == 0:
            return 0
        return int(float(self.votes_up) / votes_count * 100)

    def __json__(self):
        return {
            'votes_up': self.votes_up,
            'votes_down': self.votes_down,
        }


class MovedArtifact(Artifact):

    class __mongometa__:
        session = artifact_orm_session
        name = 'moved_artifact'

    _id = FieldProperty(S.ObjectId)
    app_config_id = ForeignIdProperty(
        'AppConfig', if_missing=lambda: c.app.config._id)
    app_config = RelationProperty('AppConfig')
    moved_to_url = FieldProperty(str, required=True, allow_none=False)
