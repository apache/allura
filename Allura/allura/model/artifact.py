import re
import os
import logging
import urllib
import cPickle as pickle
from collections import defaultdict
from time import sleep
from datetime import datetime
import Image
from mimetypes import guess_type

import pymongo
from pylons import c, g
from ming import Document, Session, Field
from ming import schema as S
from ming import orm
from ming.orm import mapper, state, session
from ming.orm.mapped_class import MappedClass, MappedClassMeta
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from ming.utils import LazyProperty
from pymongo.errors import OperationFailure
from webhelpers import feedgenerator as FG

from allura.lib import helpers as h
from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session
from .types import ArtifactReference, ArtifactReferenceType

from filesystem import File

log = logging.getLogger(__name__)

class ArtifactLink(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='artifact_link'
        indexes = [
            ('link', 'project_id') ]

    core_re = r'''(\[
            (?:(?P<project_id>.*?):)?      # optional project ID
            (?:(?P<app_id>.*?):)?      # optional tool ID
            (?P<artifact_id>.*)             # artifact ID
    \])'''

    re_link_1 = re.compile(r'\s' + core_re, re.VERBOSE)
    re_link_2 = re.compile(r'^' +  core_re, re.VERBOSE)

    _id = FieldProperty(str)
    link = FieldProperty(str)
    project_id = ForeignIdProperty('Project')
    tool_name = FieldProperty(str)
    mount_point = FieldProperty(str)
    url = FieldProperty(str)
    artifact_reference = FieldProperty(ArtifactReferenceType)

    @classmethod
    def add(cls, artifact):
        aid = artifact.index_id()
        entry = cls.query.get(_id=aid)
        kw = dict(
            link=artifact.shorthand_id(),
            project_id=artifact.project_id,
            tool_name=artifact.app_config.tool_name,
            mount_point=artifact.app_config.options.mount_point,
            url=artifact.url(),
            artifact_reference = artifact.dump_ref())
        if entry is None:
            entry = cls(_id=aid, **kw)
        for k,v in kw.iteritems():
            setattr(entry, k, v)

    @classmethod
    def remove(cls, artifact):
        mapper(cls).remove(dict(_id=artifact.index_id()))

    @classmethod
    def _parse_link(cls, s):
        s = s.strip()
        if s.startswith('['):
            s = s[1:]
        if s.endswith(']'):
            s = s[:-1]
        parts = s.split(':')
        if len(parts) == 3:
            return dict(
                project=parts[0],
                app=parts[1],
                artifact=parts[2])
        elif len(parts) == 2:
            return dict(
                project=None,
                app=parts[0],
                artifact=parts[1])
        elif len(parts) == 1:
            return dict(
                project=None,
                app=None,
                artifact=parts[0])
        else:
            return None


    @classmethod
    def lookup_links(cls, links):
        # Parse all the links
        parsed_links = dict(
            (link, cls._parse_link(link))
            for link in links)
        # Categorize links by the artifact (shortlink)
        links_by_artifact=  defaultdict(list)
        for link, parsed in parsed_links.iteritems():
            links_by_artifact[parsed['artifact']].append(link)
        # Classify potential matches by the artifact (shortlink)
        potential_matches_by_artifact = defaultdict(list)
        for al in cls.query.find(dict(
                link={'$in':links_by_artifact.keys()})):
            potential_matches_by_artifact[al.link].append(al)
        # Lookup all projects in this hierarchy
        projects_by_shortname = dict(
            (p.shortname, p) for p in c.project.project_hierarchy)
        result = dict((link, None) for link in links)
        for link, pl in parsed_links.iteritems():
            potential_matches = potential_matches_by_artifact[pl['artifact']]
            if not potential_matches: continue
            # Determine projects to search for this shortlink
            if pl['project'] is None:
                if c.project:
                    project_ids = [p._id for p in c.project.parent_iter()]
                else:
                    continue
            else:
                if pl['project'].startswith('/'):
                    shortname = pl['project'][1:]
                elif c.project:
                    shortname = os.path.join(c.project.shortname, pl['project'])
                    shortname = os.path.normpath(shortname)
                else:
                    shortname = pl['project']
                p = projects_by_shortname.get(shortname)
                if p is None: continue
                project_ids = [p._id]
            # Determine if there are any matches
            for pid in project_ids:
                potential_pid_matches = [
                    m for m in potential_matches if m.project_id == pid ]
                match = None
                for m in potential_pid_matches:
                    if pl['app'] in (None, m.mount_point):
                        match = m
                        break
                if match:
                    result[link] = match
                    break
                for m in potential_pid_matches:
                    if pl['app'] == m.tool_name:
                        result[link] = match
                        break
        return result

    @classmethod
    def lookup(cls, link):
        from .project import Project
        #
        # Parse the link syntax
        #
        m = cls.re_link_1.match(link)
        if m is None: m = cls.re_link_2.match(link)
        if m is None: return None
        groups = m.groupdict()
        project_id = groups.get('project_id', None)
        app_id = groups.get('app_id', None)
        artifact_id = groups.get('artifact_id', None)
        if app_id is None:
            app_id = project_id
            project_id = None

        #
        # Find the projects to search
        #
        if project_id is None:
            if c.project:
                projects = list(c.project.parent_iter())
            else:
                return None
        elif project_id.startswith('/'):
            projects = Project.query.find(dict(shortname=project_id[1:], deleted=False)).all()
        else:
            if c.project:
                project_id = os.path.normpath(
                    os.path.join('/' + c.project.shortname, project_id))
            else:
                project_id = '/' + project_id
            projects = Project.query.find(dict(shortname=project_id[1:], deleted=False)).all()
        if not projects: return None
        #
        # Actually search the projects
        #
        with h.push_config(c, project=projects[0]):
            for p in projects:
                links = [
                    l for l in cls.query.find(dict(project_id=p._id, link=artifact_id))
                    if ArtifactReference(l.artifact_reference).artifact ]
                for l in links:
                    if app_id is None: return l
                    if app_id == l.mount_point: return l
                for l in links:
                    if app_id == l.tool_name: return l
        return None

class Feed(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name = 'artifact_feed'
        indexes = [ 'pubdate' ]

    _id = FieldProperty(S.ObjectId)
    artifact_reference = FieldProperty(ArtifactReferenceType)
    title=FieldProperty(str)
    link=FieldProperty(str)
    pubdate = FieldProperty(datetime, if_missing=datetime.utcnow)
    description = FieldProperty(str)
    unique_id = FieldProperty(str, if_missing=lambda:h.nonce(40))
    author_name = FieldProperty(str, if_missing=lambda:c.user.display_name)
    author_link = FieldProperty(str, if_missing=lambda:c.user.url())

    @classmethod
    def post(cls, artifact, title=None, description=None):
        idx = artifact.index()
        if title is None:
            title='%s modified by %s' % (idx['title_s'], c.user.display_name)
        if description is None: description = title
        item = cls(artifact_reference=artifact.dump_ref(),
                   title=title,
                   description=description,
                   link=artifact.url())
        return item

    @classmethod
    def feed(cls, q, feed_type, title, link, description,
             since=None, until=None, offset=None, limit=None):
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
        if limit is not None: query = cur.limit(limit)
        if offset is not None: query = cur.offset(limit)
        for r in cur:
            feed.add_item(title=r.title,
                          link=h.absurl(r.link),
                          pubdate=r.pubdate,
                          description=r.description,
                          unique_id=r.unique_id,
                          author_name=r.author_name,
                          author_link=h.absurl(r.author_link))
        return feed

class Artifact(MappedClass):
    class __mongometa__:
        session = artifact_orm_session
        name='artifact'
        indexes = [ 'app_config_id' ]
        def before_save(data):
            data['mod_date'] = datetime.utcnow()
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
    tags = FieldProperty([dict(tag=str, count=int)])
    labels = FieldProperty([str])
    references = FieldProperty([ArtifactReferenceType])
    backreferences = FieldProperty({str:ArtifactReferenceType})
    app_config = RelationProperty('AppConfig')

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
    def artifacts_tagged_with(cls, tag):
        return cls.query.find({'tags.tag':tag})

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

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = ArtifactReference(dict(
                    project_id=self.app_config.project._id,
                    mount_point=self.app_config.options.mount_point,
                    artifact_type=pymongo.bson.Binary(pickle.dumps(self.__class__)),
                    artifact_id=self._id))
            return d
        except AttributeError:
            return None

    def add_tags(self, tags):
        'Update the tags collection to reflect new tags added'
        cur_tags = dict((t['tag'], t['count']) for t in self.tags)
        for t in tags:
            c = cur_tags.get(t, 0)
            c += 1
            cur_tags[t] = c
        self.tags = [ dict(tag=k, count=v) for k,v in cur_tags.iteritems() ]

    def remove_tags(self, tags):
        'Update the tags collection to reflect tags removed'
        cur_tags = dict((t['tag'], t['count']) for t in self.tags)
        for t in tags:
            c = cur_tags.get(t, 1)
            c -= 1
            if c:
                cur_tags[t] = c
            else:
                cur_tags.pop(t, None)
        self.tags = [ dict(tag=k, count=v) for k,v in cur_tags.iteritems() ]

    @property
    def project(self):
        return self.app_config.project

    @property
    def project_id(self):
        return self.app_config.project_id

    @property
    def app(self):
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
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id.replace('.', '/')

    def index(self):
        project = self.project
        return dict(
            id=self.index_id(),
            mod_date_dt=self.mod_date,
            title_s='Artifact %s' % self._id,
            project_id_s=project._id,
            project_name_t=project.name,
            project_shortname_t=project.shortname,
            tool_name_s=self.app_config.tool_name,
            mount_point_s=self.app_config.options.mount_point,
            is_history_b=False,
            url_s=self.url(),
            type_s=self.type_s,
            tags_t=','.join(t['tag'] for t in self.tags),
            labels_t=','.join(l for l in self.labels),
            snippet_s='')

    def url(self):
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
        return Thread.query.get(artifact_reference=self.dump_ref())

    @LazyProperty
    def discussion_thread(self):
        return self.get_discussion_thread()

class Snapshot(Artifact):
    class __mongometa__:
        session = artifact_orm_session
        name='artifact_snapshot'
        unique_indexes = [ ('artifact_class', 'artifact_id', 'version') ]

    _id = FieldProperty(S.ObjectId)
    artifact_id = FieldProperty(S.ObjectId)
    artifact_class = FieldProperty(str)
    version = FieldProperty(S.Int, if_missing=0)
    author = FieldProperty(dict(
            id=S.ObjectId,
            username=str,
            display_name=str))
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
    class __mongometa__:
        session = artifact_orm_session
        name='versioned_artifact'
        history_class = Snapshot

    version = FieldProperty(S.Int, if_missing=0)

    def commit(self):
        '''Save off a snapshot of the artifact and increment the version #'''
        self.version += 1
        data = dict(
            artifact_id=self._id,
            artifact_class='%s.%s' % (
                self.__class__.__module__,
                self.__class__.__name__),
            version=self.version,
            author=dict(
                id=c.user._id,
                username=c.user.username,
                display_name=c.user.display_name),
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
            author_display_name_t=author.display_name,
            timestamp_dt=self.timestamp,
            text=self.text)
        return result

    def shorthand_id(self):
        return self.slug

class AwardFile(File):
    class __mongometa__:
        session = main_orm_session
        name = 'award_file.files'

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            award_id=S.ObjectId,
            filename=str))

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
        return AwardFile.query.find({'metadata.award_id':self._id}).first()

    def url(self):
        return urllib.unquote_plus(str(self.short))

    def longurl(self):
        slug = str(self.created_by_neighborhood.url_prefix + "_admin/awards/" + self.short)
        return urllib.unquote_plus(slug)

    def shorthand_id(self):
        return self.short

class AwardGrant(Artifact):
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
        return AwardFile.query.find({'metadata.award_id':self.award_id}).first()

    def url(self):
        slug = str(self.granted_to_project.shortname).replace('/','_')
        return urllib.unquote_plus(slug)

    def longurl(self):
        slug = str(self.granted_to_project.shortname).replace('/','_')
        slug = str(self.granted_by_neighborhood.url_prefix + "_admin/awards/"
            + self.award.short + '/' + slug)
        return urllib.unquote_plus(slug)

    def shorthand_id(self):
        if self.award:
            return self.award.short
        else:
            return None

class BaseAttachment(File):
    thumbnail_size = (255, 255)

    class __mongometa__:
        name = 'attachment.files'
        session = project_orm_session
        indexes = ['metadata.filename']

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            artifact_id=S.ObjectId,
            app_config_id=S.ObjectId,
            type=str,
            filename=str))

    def url(self):
        return self.artifact.url() + 'attachment/' + self.filename

    def is_embedded(self):
        from pylons import request
        return self.metadata.filename in request.environ.get('allura.macro.att_embedded', [])

    @classmethod
    def create_with_thumbnail(cls, file_info, artifact_id, artifact_id_name):
        if h.supported_by_PIL(file_info.type):
            meta = dict(type="thumbnail", app_config_id=c.app.config._id)
            meta[artifact_id_name] = artifact_id
            original_meta = dict(type="attachment", app_config_id=c.app.config._id)
            original_meta[artifact_id_name] = artifact_id
            h.save_image(file_info, cls, square=True, thumbnail_size=cls.thumbnail_size, save_original=True,
                         meta=meta, original_meta=original_meta)
        else:
            filename = file_info.filename
            content_type = guess_type(filename)
            if content_type: content_type = content_type[0]
            else: content_type = 'application/octet-stream'
            args = dict(content_type=content_type,
                        filename=filename,
                        type="attachment",
                        app_config_id=c.app.config._id)
            args[artifact_id_name] = artifact_id
            with cls.create(**args) as fp:
                while True:
                    s = file_info.file.read()
                    if not s: break
                    fp.write(s)
