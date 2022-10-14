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
import typing

import pymongo
from tg import tmpl_context as c, app_globals as g
from tg import request
from ming import schema as S
from ming.orm import state, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty
from ming.orm.declarative import MappedClass
from ming.utils import LazyProperty
import feedgenerator as FG

from allura.lib import helpers as h
from allura.lib import security
from allura.lib import utils
from allura.lib import plugin
from allura.lib import exceptions as forge_exc
from allura.lib.decorators import memoize
from allura.lib.search import SearchIndexable
from .session import main_orm_session
from .session import project_orm_session
from .session import artifact_orm_session
from .index import ArtifactReference
from .types import ACL, MarkdownCache
from .project import AppConfig
from .notification import MailFooter

from .filesystem import File
import six

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query

log = logging.getLogger(__name__)


class Artifact(MappedClass, SearchIndexable):

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

    query: 'Query[Artifact]'

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

    def __json__(self, posts_limit=None, is_export=False, user=None):
        """Return a JSON-encodable :class:`dict` representation of this
        Artifact.

        """
        return dict(
            _id=str(self._id),
            mod_date=self.mod_date,
            labels=list(self.labels),
            related_artifacts=[a.url() for a in self.related_artifacts(user=user or c.user)],
            discussion_thread=self.discussion_thread.__json__(limit=posts_limit, is_export=is_export),
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
        raise NotImplementedError('attachment_class')

    @LazyProperty
    def ref(self):
        """Return :class:`allura.model.index.ArtifactReference` for this
        Artifact.

        """
        if hasattr(self, '_ref'):
            return self._ref

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
        if hasattr(self, '_backrefs'):
            return self._backrefs

        q = ArtifactReference.query.find(dict(references=self.index_id()))
        return [aref._id for aref in q]

    def related_artifacts(self, user=None):
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
            try:
                if user and not h.has_access(artifact, 'read', user):
                    continue
            except Exception:
                log.debug('Error doing permission check on related artifacts of {}, '
                          'probably because the "artifact" is a Commit not a real artifact'.format(self.index_id()),
                          exc_info=True)

            # TODO: This should be refactored. We shouldn't be checking
            # artifact type strings in platform code.
            if artifact.type_s == 'Commit' and not artifact.repo:
                ac = AppConfig.query.get(_id=ref.artifact_reference['app_config_id'])
                app = ac.project.app_instance(ac) if ac else None
                if app:
                    artifact.set_context(app.repo)
            if artifact not in related_artifacts and (getattr(artifact, 'deleted', False) is False):
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
        return Mailbox.subscribe(
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

    @memoize  # since its called many times from edit_post.html within threaded comments
    def subscribed(self, user=None, include_parents=True):
        from allura.model import Mailbox
        if user is None:
            user = c.user
        user_proj_app_q = dict(user_id=user._id,
                               project_id=self.app_config.project_id,
                               app_config_id=self.app_config._id)
        art_subscribed = Mailbox.subscribed(artifact=self, **user_proj_app_q)
        if art_subscribed:
            return True
        if include_parents:
            tool_subscribed = Mailbox.subscribed(**user_proj_app_q)
            if tool_subscribed:
                return True
        return False

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
            return 'mailto:{}?subject=[{}:{}:{}] Re: {}'.format(
                self.email_address,
                self.app_config.project.shortname,
                self.app_config.options.mount_point,
                self.shorthand_id(),
                subject)
        else:
            return 'mailto:%s' % self.email_address

    @property
    def email_domain(self):
        """Return domain part of email address for this Artifact"""
        url = self.app.url[1:-1].split('/')
        return '.'.join(reversed(url)).replace('_', '-')

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

    def index(self):
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

    @property
    def type_name(self):
        """
        :return: a presentation name for this type of artifact
        :rtype: str
        """
        return self.type_s.lower()

    def url(self):
        """Return the URL for this Artifact.

        Subclasses must implement this.

        """
        raise NotImplementedError('url')  # pragma no cover

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
        threads = Thread.query.find(dict(ref_id=self.index_id())).all()
        if not threads:
            idx = self.index()
            t = Thread.new(
                app_config_id=self.app_config_id,
                discussion_id=self.app_config.discussion_id,
                ref_id=idx['id'],
                subject='%s discussion' % h.get_first(idx, 'title'))
        elif len(threads) == 1:
            t = threads[0]
        else:
            # there should not be multiple threads, we'll merge them
            destination = threads.pop()
            for thread in threads:
                for post in thread.posts:
                    post.thread_id = destination._id
                    destination.num_replies += 1
                    destination.last_post_date = max(destination.last_post_date, post.mod_date)
                    session(post).flush(post)
                    session(post).expunge(post)  # so thread.posts ref later in the code doesn't use stale posts
                Thread.query.remove({'_id': thread._id})  # NOT thread.delete() since that would remove its posts too
                thread.attachment_class().query.update({'thread_id': thread._id},
                                                       {'$set': {'thread_id': destination._id}},
                                                       multi=True)
            t = destination

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
        :param kw: passed through to Attachment class constructor

        """
        att = self.attachment_class().save_attachment(
            filename=filename,
            fp=fp, artifact_id=self._id, **kw)
        return att

    @LazyProperty
    def attachments(self):
        if hasattr(self, '_attachments'):
            atts = self._attachments
        else:
            atts = self.attachment_class().query.find(dict(
                app_config_id=self.app_config_id, artifact_id=self._id, type='attachment')).all()
        return utils.unique_attachments(atts)

    def delete(self):
        """Delete this Artifact.

        """
        ArtifactReference.query.remove(dict(_id=self.index_id()))
        super().delete()

    def get_mail_footer(self, notification, toaddr):
        allow_email_posting = self.app.config.options.get('AllowEmailPosting', True)
        return MailFooter.standard(notification, allow_email_posting)

    def message_id(self):
        '''Persistent, email-friendly (Message-ID header) id of this artifact'''
        return h.gen_message_id(self._id)

    @classmethod
    def is_limit_exceeded(cls, app_config, user=None, count_by_user=None):
        """
        Returns True if any of artifact creation rate limits are exceeded,
        False otherwise
        """
        pkg = cls.__module__.split('.', 1)[0]
        opt = f'{pkg}.rate_limits'

        def count_in_app():
            return cls.query.find(dict(app_config_id=app_config._id)).count()
        provider = plugin.ProjectRegistrationProvider.get()
        start = provider.registration_date(app_config.project)

        try:
            h.rate_limit(opt, count_in_app, start)
            if user and not user.is_anonymous() and count_by_user is not None:
                h.rate_limit(opt + '_per_user', count_by_user, user.registration_date())
        except forge_exc.RatelimitError:
            return True
        return False


class Snapshot(Artifact):
    """
    A snapshot of an :class:`Artifact <allura.model.artifact.Artifact>`,
    used in :class:`VersionedArtifact <allura.model.artifact.VersionedArtifact>`
    """
    class __mongometa__:
        session = artifact_orm_session
        name = 'artifact_snapshot'
        unique_indexes = [('artifact_class', 'artifact_id', 'version')]
        indexes = [('artifact_id', 'version'),
                   'author.id',
                   ]

    query: 'Query[Snapshot]'

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
            result['title'] = '%s (version %d)' % (h.get_first(original_index, 'title'), self.version)
        else:
            result['title'] = None
        result.update(
            id=self.index_id(),
            version_i=self.version,
            author_username_t=self.author.username,
            author_display_name_t=self.author.display_name,
            timestamp_dt=self.timestamp,
            is_history_b=True)
        return result

    def original(self):
        raise NotImplementedError('original')  # pragma no cover

    def shorthand_id(self):
        return f'{self.original().shorthand_id()}#{self.version}'

    def clear_user_data(self):
        """ Redact author data for a given user """

        new_author = {
            "username": "",
            "display_name": "",
            "id": None,
            "logged_ip": None
        }
        self.author = new_author

    @classmethod
    def from_username(cls, username):
        return cls.query.find({'author.username': username}).all()

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

    query: 'Query[VersionedArtifact]'

    version = FieldProperty(S.Int, if_missing=0)

    def commit(self, update_stats=True):
        '''Save off a snapshot of the artifact and increment the version #'''
        try:
            ip_address = utils.ip_address(request)
        except Exception:
            ip_address = '0.0.0.0'
        data = dict(
            artifact_id=self._id,
            artifact_class='{}.{}'.format(
                self.__class__.__module__,
                self.__class__.__name__),
            author=dict(
                id=c.user._id,
                username=c.user.username,
                display_name=c.user.get_pref('display_name'),
                logged_ip=ip_address),
            data=state(self).clone())
        while True:
            self.version += 1
            data['version'] = self.version
            data['timestamp'] = datetime.utcnow()
            ss = self.__mongometa__.history_class(**data)
            try:
                session(ss).insert_now(ss, state(ss))
            except pymongo.errors.DuplicateKeyError:
                log.warning('Trying to create duplicate version %s of %s',
                            self.version, self.__class__)
                session(ss).expunge(ss)
                continue
            else:
                break
        log.debug('Snapshot version %s of %s',
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
            artifact_class='{}.{}'.format(
                self.__class__.__module__,
                self.__class__.__name__),
            version=n)
        if ss is None:
            raise IndexError(n)
        return ss

    def revert(self, version):
        ss = self.get_version(version)
        old_version = self.version
        for k, v in ss.data.items():
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
        super().delete()
        HC = self.__mongometa__.history_class
        HC.query.remove(dict(artifact_id=self._id))

    @classmethod
    def is_limit_exceeded(cls, *args, **kwargs):
        if 'user' in kwargs:
            def distinct_artifacts_by_user():
                # count distinct items, not total (e.g. many edits to a single wiki page doesn't count against you)
                # query history here, as regular base artifacts have no author information
                HC = cls.__mongometa__.history_class
                artifacts = HC.query.find({'author.id': kwargs['user']._id}).distinct('artifact_id')
                """
                # some useful debugging:
                log.info(artifacts)
                for art_id in artifacts:
                    art = cls.query.get(_id=art_id)
                    log.info('   ' + art.url())
                """
                return len(artifacts)
            kwargs['count_by_user'] = distinct_artifacts_by_user
        return super().is_limit_exceeded(*args, **kwargs)


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

    query: 'Query[Message]'

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
        dt = timestamp.strftime('%Y%m%d%H%M%S%f')
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

    query: 'Query[AwardFile]'

    award_id = FieldProperty(S.ObjectId)


class Award(Artifact):

    class __mongometa__:
        session = main_orm_session
        name = 'award'
        indexes = ['short']

    query: 'Query[Award]'

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
        result['created_by_s'] = self.created_by.name if self.created_by else None
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

    query: 'Query[AwardGrant]'

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
    award_url = FieldProperty(str, if_missing='')
    comment = FieldProperty(str, if_missing='')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)

    def index(self):
        result = Artifact.index(self)
        result.update(
            _id_s=self._id,
            short_s=self.short,
            timestamp_dt=self.timestamp,
            full_s=self.full)
        result['award_s'] = self.award.short if self.award else None
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


class RssFeed(FG.Rss201rev2Feed):
    def rss_attributes(self):
        attrs = super().rss_attributes()
        attrs['xmlns:atom'] = 'http://www.w3.org/2005/Atom'
        return attrs

    def add_root_elements(self, handler):
        super().add_root_elements(handler)
        if self.feed['feed_url'] is not None:
            handler.addQuickElement('atom:link', '', {
                'rel': 'self',
                'href': self.feed['feed_url'],
                'type': 'application/rss+xml',
            })


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
            (('author_link', pymongo.ASCENDING),
             ('pubdate', pymongo.DESCENDING)),
            # used in project feed
            (('project_id', pymongo.ASCENDING),
             ('pubdate', pymongo.DESCENDING)),
        ]

    query: 'Query[Feed]'

    _id = FieldProperty(S.ObjectId)
    ref_id: str = ForeignIdProperty('ArtifactReference')
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

    def clear_user_data(self):
        """ Redact author data """
        self.author_name = ""
        self.author_link = ""
        title_parts = self.title.partition(" modified by ")
        self.title = "".join(title_parts[0:2]) + ("<REDACTED>" if title_parts[2] else '')

    @classmethod
    def from_username(cls, username):
        return cls.query.find({'author_link': f"/u/{username}/"}).all()

    @classmethod
    def has_access(cls, artifact):
        # Enable only for development.
        # return True
        from allura import model as M
        anon = M.User.anonymous()
        if not security.has_access(artifact, 'read', user=anon):
            return False
        if not security.has_access(c.project, 'read', user=anon):
            return False
        return True

    @classmethod
    def post(cls, artifact, title=None, description=None, author=None,
             author_link=None, author_name=None, pubdate=None, link=None, **kw):
        """
        Create a Feed item.  Returns the item.
        But if anon doesn't have read access, create does not happen and None is
        returned.
        """
        if not Feed.has_access(artifact):
            return
        idx = artifact.index()
        if author is None:
            author = c.user
        if author_name is None:
            author_name = author.get_pref('display_name')
        if title is None:
            title = '{} modified by {}'.format(
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
             since=None, until=None, page=None, limit=None):
        "Produces feedgenerator Feed"
        d = dict(title=title, link=h.absurl(h.urlquote(link)),
                 description=description, language='en',
                 feed_url=request.url)
        if feed_type == 'atom':
            feed = FG.Atom1Feed(**d)
        elif feed_type == 'rss':
            feed = RssFeed(**d)
        limit, page = h.paging_sanitizer(limit or 10, page)
        query = defaultdict(dict)
        if callable(q):
            q = q(since, until, page, limit)
        query.update(q)
        if since is not None:
            query['pubdate']['$gte'] = since
        if until is not None:
            query['pubdate']['$lte'] = until
        cur = cls.query.find(query)
        cur = cur.sort('pubdate', pymongo.DESCENDING)
        cur = cur.limit(limit)
        cur = cur.skip(limit * page)
        for r in cur:
            feed.add_item(title=r.title,
                          link=h.absurl(h.urlquote_path_only(r.link)),
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

    query: 'Query[VotableArtifact]'

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


class ReactableArtifact(MappedClass):

    """Reaction support for the Artifact. Use as a mixin."""

    react_counts = FieldProperty({str: None}, if_missing=dict())
    # dict to store reaction counts
    react_users = FieldProperty({str: None}, if_missing=dict())
    # dict to store reactions vs usernames

    def post_reaction(self, r, user):
        current_reaction = self.user_reacted(user)
        if current_reaction is None:
            # no prev reactions. simply append
            if r in self.react_users:
                self.react_users[r].append(user.username)
            else:
                self.react_users[r] = [user.username]
            self.update_react_count(r)
        elif current_reaction == r:
            # prev=current so remove
            self.react_users[r].remove(user.username)
            self.update_react_count(r, add=False)
            if len(self.react_users[r]) == 0:
                self.react_users.pop(r)
        else:
            # prev!=currnet so remove prev then append
            self.react_users[current_reaction].remove(user.username)
            if r in self.react_users:
                self.react_users[r].append(user.username)
            else:
                self.react_users[r] = [user.username]
            self.update_react_count(current_reaction, add=False)
            self.update_react_count(r)
            if len(self.react_users[current_reaction]) == 0:
                self.react_users.pop(current_reaction)

    def user_reacted(self, user):
        for i in self.react_users:
            if user.username in self.react_users[i]:
                return i
        return

    def update_react_count(self, r, add=True):
        i = 1
        if not add:
            i = -1
        if r in self.react_counts:
            self.react_counts[r] += i
            if self.react_counts[r] == 0:
                self.react_counts.pop(r)
        else:
            self.react_counts[r] = 1


class MovedArtifact(Artifact):

    class __mongometa__:
        session = artifact_orm_session
        name = 'moved_artifact'

    query: 'Query[MovedArtifact]'

    _id = FieldProperty(S.ObjectId)
    app_config_id = ForeignIdProperty(
        'AppConfig', if_missing=lambda: c.app.config._id)
    app_config = RelationProperty('AppConfig')
    moved_to_url = FieldProperty(str, required=True, allow_none=False)


class SpamCheckResult(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'spam_check_result'
        indexes = [
            ('project_id', 'result'),
            ('user_id', 'result'),
        ]

    query: 'Query[SpamCheckResult]'

    _id = FieldProperty(S.ObjectId)
    ref_id: str = ForeignIdProperty('ArtifactReference')
    ref = RelationProperty('ArtifactReference', via='ref_id')
    project_id = ForeignIdProperty('Project')
    project = RelationProperty('Project', via='project_id')
    user_id = ForeignIdProperty('User')
    user = RelationProperty('User', via='user_id')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    result = FieldProperty(bool)
