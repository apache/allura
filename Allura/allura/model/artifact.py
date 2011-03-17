import logging
import urllib
import cPickle as pickle
from collections import defaultdict
from datetime import datetime

import bson
import pymongo
from pylons import c, request
from ming import schema as S
from ming.orm import state, session
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from ming.utils import LazyProperty
from webhelpers import feedgenerator as FG

from allura.lib import helpers as h
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session
from .index import ArtifactReference

from filesystem import File

log = logging.getLogger(__name__)

class Artifact(MappedClass):
    """
    The base class for anything you want to keep track of.

    It will automatically be added to solr (see index() method).  It also
    gains a discussion thread and can have files attached to it.

    :var tool_version: default's to the app's version
    :var acl: dict of permission name => [roles]
    :var labels: list of plain old strings
    :var references: list of outgoing references to other tickets
    :var backreferences: dict of incoming references to this artifact, mapped by solr id
    """

    class __mongometa__:
        session = artifact_orm_session
        name='artifact'
        indexes = [ 'app_config_id' ]
        def before_save(data):
            if not getattr(artifact_orm_session._get(), 'skip_mod_date', False):
                data['mod_date'] = datetime.utcnow()
            else:
                log.debug('Not updating mod_date')
            if c.project:
                c.project.last_updated = datetime.utcnow()
    type_s = 'Generic Artifact'

    # Artifact base schema
    _id = FieldProperty(S.ObjectId)
    mod_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:c.app.config._id)
    plugin_verson = FieldProperty(S.Deprecated)
    tool_version = FieldProperty(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.tool_name:c.app.__version__})
    acl = FieldProperty({str:[S.ObjectId]})
    tags = FieldProperty(S.Deprecated)
    labels = FieldProperty([str])
    references = FieldProperty(S.Deprecated)
    backreferences = FieldProperty(S.Deprecated)
    app_config = RelationProperty('AppConfig')

    @classmethod
    def attachment_class(cls):
        raise NotImplementedError, 'attachment_class'

    @classmethod
    def translate_query(cls, q, fields):
        for f in fields:
            if f[-2] == '_':
                base = f[:-2]
                actual = f
                q = q.replace(base+':', actual+':')
        return q

    @LazyProperty
    def ref(self):
        return ArtifactReference.from_artifact(self)

    @LazyProperty
    def refs(self):
        return self.ref.references

    @LazyProperty
    def backrefs(self):
        q = ArtifactReference.query.find(dict(references=self))
        return [ aref._id for aref in q ]

    def subscribe(self, user=None, topic=None, type='direct', n=1, unit='day'):
        from allura.model import Mailbox
        if user is None: user = c.user
        Mailbox.subscribe(
            user_id=user._id,
            project_id=self.app_config.project_id,
            app_config_id=self.app_config._id,
            artifact=self, topic=topic,
            type=type, n=n, unit=unit)

    def unsubscribe(self, user=None):
        from allura.model import Mailbox
        if user is None: user = c.user
        Mailbox.unsubscribe(
            user_id=user._id,
            project_id=self.app_config.project_id,
            app_config_id=self.app_config._id,
            artifact_index_id=self.index_id())

    def primary(self, primary_class):
        '''If an artifact is a "secondary" artifact (discussion of a ticket, for
        instance), return the artifact that is the "primary".
        '''
        return self

    @classmethod
    def artifacts_labeled_with(cls, label):
        return cls.query.find({'labels':label})

    def email_link(self, subject='artifact'):
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
        return self.app_config.project

    @property
    def project_id(self):
        return self.app_config.project_id

    @LazyProperty
    def app(self):
        if getattr(c, 'app', None) and c.app.config._id == self.app_config._id:
            return c.app
        else:
            ac = self.app_config
            return self.app_config.load()(self.project, self.app_config)

    def give_access(self, *access_types, **kw):
        user = kw.pop('user', c.user)
        project = kw.pop('project', c.project)
        with h.push_config(c, project=project):
            project_role_id = user.project_role()._id
        for at in access_types:
            l = self.acl.setdefault(at, [])
            if project_role_id not in l:
                l.append(project_role_id)

    def revoke_access(self, *access_types, **kw):
        user = kw.pop('user', c.user)
        project = kw.pop('project', c.project)
        with h.push_config(c, project=project):
            project_role_id = user.project_role()._id
        for at in access_types:
            l = self.acl.setdefault(at, [])
            if project_role_id in l:
                l.remove(project_role_id)

    def index_id(self):
        "Used for solr search indexing"
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    def index(self):
        """
        Subclasses should override this, providing a dictionary of solr_field => value.
        These fields & values will be stored by solr.  Subclasses should call the
        super() index() and then extend it with more fields.  All these fields will be
        included in the 'text' field (done by search.solarize())

        The _s and _t suffixes, for example, follow solr dynamic field naming
        pattern.
        You probably want to override at least title_s and text to have
        meaningful search results and email senders.
        """

        project = self.project
        return dict(
            id=self.index_id(),
            mod_date_dt=self.mod_date,
            title_s='Artifact %s' % self._id,
            project_id_s=str(project._id),
            project_name_t=project.name,
            project_shortname_t=project.shortname,
            tool_name_s=self.app_config.tool_name,
            mount_point_s=self.app_config.options.mount_point,
            is_history_b=False,
            url_s=self.url(),
            type_s=self.type_s,
            labels_t=' '.join(l for l in self.labels),
            snippet_s='')

    def url(self):
        """
        Subclasses should implement this, providing the URL to the artifact
        """
        raise NotImplementedError, 'url' # pragma no cover

    def shorthand_id(self):
        '''How to refer to this artifact within the app instance context.

        For a wiki page, it might be the title.  For a ticket, it might be the
        ticket number.  For a discussion, it might be the message ID.  Generally
        this should have a strong correlation to the URL.
        '''
        return str(self._id) # pragma no cover

    def get_discussion_thread(self, data=None):
        '''Return the discussion thread for this artifact (possibly made more
        specific by the message_data)'''
        from .discuss import Thread
        return Thread.query.get(ref_id=self.index_id())

    @LazyProperty
    def discussion_thread(self):
        return self.get_discussion_thread()

    def attach(self, filename, fp, **kw):
        att = self.attachment_class().save_attachment(
            filename=filename,
            fp=fp, artifact_id=self._id, **kw)
        return att

class Snapshot(Artifact):
    """A snapshot of an :class:`Artifact <allura.model.artifact.Artifact>`, used in :class:`VersionedArtifact <allura.model.artifact.VersionedArtifact>`"""
    class __mongometa__:
        session = artifact_orm_session
        name='artifact_snapshot'
        unique_indexes = [ ('artifact_class', 'artifact_id', 'version') ]
        indexes = [ ('artifact_id', 'version') ]

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
        result.update(self.original().index())
        result.update(
            id=self.index_id(),
            version_i=self.version,
            author_username_t=self.author.username,
            author_display_name_t=self.author.display_name,
            timestamp_dt=self.timestamp,
            is_history_b=True)
        return result

    def original(self):
        raise NotImplemented, 'original' # pragma no cover

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def __getattr__(self, name):
        return getattr(self.data, name)

class VersionedArtifact(Artifact):
    """
    An :class:`Artifact <allura.model.artifact.Artifact>` that has versions.
    Associated data like attachments and discussion thread are not versioned.
    """
    class __mongometa__:
        session = artifact_orm_session
        name='versioned_artifact'
        history_class = Snapshot

    version = FieldProperty(S.Int, if_missing=0)
    # Not null if artifact originated from external batch import
    import_id = FieldProperty(S.ObjectId, if_missing=None)

    def commit(self):
        '''Save off a snapshot of the artifact and increment the version #'''
        self.version += 1
        try:
            ip_address = request.headers.get('X_FORWARDED_FOR', request.remote_addr)
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
            data=state(self).document.deinstrumented_clone())
        ss = self.__mongometa__.history_class(**data)
        session(ss).insert_now(ss, state(ss))
        log.info('Snapshot version %s of %s',
                 self.version, self.__class__)
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
        for k,v in ss.data.iteritems():
            setattr(self, k, v)
        self.version = old_version

    def history(self):
        HC = self.__mongometa__.history_class
        q = HC.query.find(dict(artifact_id=self._id)).sort('version', pymongo.DESCENDING)
        return q

    @property
    def last_updated(self):
        history = self.history()
        if len(history):
            return self.history().first().timestamp
        else:
            return self.mod_date

class Message(Artifact):
    """
    A message

    :var _id: an email friendly (e.g. message-id) string id
    :var slug: slash-delimeted random identifier.  Slashes useful for threaded searching and ordering
    :var full_slug: string of slash-delimited "timestamp:slug" components.  Useful for sorting by timstamp
    """

    class __mongometa__:
        session = artifact_orm_session
        name='message'
        indexes = Artifact.__mongometa__.indexes + [ 'slug', 'parent_id', 'timestamp' ]
    type_s='Generic Message'

    _id=FieldProperty(str, if_missing=h.gen_message_id)
    slug=FieldProperty(str, if_missing=h.nonce)
    full_slug=FieldProperty(str, if_missing=None)
    parent_id=FieldProperty(str)
    app_id=FieldProperty(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id=FieldProperty(S.ObjectId, if_missing=lambda:c.user._id)
    text=FieldProperty(str, if_missing='')

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
        return User.query.get(_id=self.author_id) or User.anonymous

    def reply(self):
        new_id = h.gen_message_id()
        slug, full_slug = self.make_slugs(self)
        new_args = dict(
            state(self).document,
            _id=new_id,
            slug=slug,
            full_slug=full_slug,
            parent_id=self._id,
            timestamp=datetime.utcnow(),
            author_id=c.user._id)
        return self.__class__(**new_args)

    def descendants(self):
        q = self.query.find(dict(slug={'$gt':self.slug})).sort('slug')
        for msg in q:
            if msg.slug.startswith(self.slug):
                yield msg
            else:
                break

    def replies(self):
        return self.query.find(dict(parent_id=self._id))

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
    award_id=FieldProperty(S.ObjectId)

class Award(Artifact):
    class __mongometa__:
        session = main_orm_session
        name='award'
        indexes = [ 'short' ]
    type_s = 'Generic Award'

    from .project import Neighborhood
    _id=FieldProperty(S.ObjectId)
    created_by_neighborhood_id = ForeignIdProperty(Neighborhood, if_missing=None)
    created_by_neighborhood = RelationProperty(Neighborhood, via='created_by_neighborhood_id')
    short=FieldProperty(str, if_missing=h.nonce)
    timestamp=FieldProperty(datetime, if_missing=datetime.utcnow)
    full=FieldProperty(str, if_missing='')

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
        return urllib.quote(str(self.short))

    def longurl(self):
        slug = str(self.created_by_neighborhood.url_prefix + "_admin/awards/" + self.short)
        return urllib.quote(slug)

    def shorthand_id(self):
        return self.short

class AwardGrant(Artifact):
    "An :class:`Award <allura.model.artifact.Award>` can be bestowed upon a project by a neighborhood"
    class __mongometa__:
        session = main_orm_session
        name='grant'
        indexes = [ 'short' ]
    type_s = 'Generic Award Grant'

    _id=FieldProperty(S.ObjectId)
    award_id = ForeignIdProperty(Award, if_missing=None)
    award = RelationProperty(Award, via='award_id')
    granted_by_neighborhood_id = ForeignIdProperty('Neighborhood', if_missing=None)
    granted_by_neighborhood = RelationProperty('Neighborhood', via='granted_by_neighborhood_id')
    granted_to_project_id = ForeignIdProperty('Project', if_missing=None)
    granted_to_project = RelationProperty('Project', via='granted_to_project_id')
    timestamp=FieldProperty(datetime, if_missing=datetime.utcnow)

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
        slug = str(self.granted_to_project.shortname).replace('/','_')
        return urllib.quote(slug)

    def longurl(self):
        slug = str(self.granted_to_project.shortname).replace('/','_')
        slug = str(self.granted_by_neighborhood.url_prefix + "_admin/awards/"
            + self.award.short + '/' + slug)
        return urllib.quote(slug)

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
            ('artifact_ref.project_id', 'artifact_ref.mount_point') ]

    _id = FieldProperty(S.ObjectId)
    ref_id = ForeignIdProperty('ArtifactReference')
    title=FieldProperty(str)
    link=FieldProperty(str)
    pubdate = FieldProperty(datetime, if_missing=datetime.utcnow)
    description = FieldProperty(str)
    unique_id = FieldProperty(str, if_missing=lambda:h.nonce(40))
    author_name = FieldProperty(str, if_missing=lambda:c.user.get_pref('display_name') if hasattr(c, 'user') else None)
    author_link = FieldProperty(str, if_missing=lambda:c.user.url() if hasattr(c, 'user') else None)

    @classmethod
    def post(cls, artifact, title=None, description=None):
        "Create a Feed item"
        idx = artifact.index()
        if title is None:
            title='%s modified by %s' % (idx['title_s'], c.user.get_pref('display_name'))
        if description is None: description = title
        item = cls(ref_id=artifact.index_id(),
                   title=title,
                   description=description,
                   link=artifact.url())
        return item

    @classmethod
    def feed(cls, q, feed_type, title, link, description,
             since=None, until=None, offset=None, limit=None):
        "Produces webhelper.feedgenerator Feed"
        d = dict(title=title, link=h.absurl(link), description=description, language=u'en')
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
        if limit is None: limit = 10
        query = cur.limit(limit)
        if offset is not None: query = cur.offset(offset)
        for r in cur:
            feed.add_item(title=r.title,
                          link=h.absurl(r.link.encode('utf-8')),
                          pubdate=r.pubdate,
                          description=r.description,
                          unique_id=r.unique_id,
                          author_name=r.author_name,
                          author_link=h.absurl(r.author_link))
        return feed
