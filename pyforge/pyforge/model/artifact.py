import re
import os
import logging
from time import sleep
from datetime import datetime
import cPickle as pickle

import pymongo
from pylons import c
from ming import Document, Session, Field
from ming import schema as S
from ming.orm.base import mapper, session, state
from ming.orm.mapped_class import MappedClass, MappedClassMeta
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from pymongo.errors import OperationFailure

from pyforge.lib.helpers import nonce, push_config, push_context
from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session

log = logging.getLogger(__name__)

def gen_message_id():
    parts = c.project.url().split('/')[1:-1]
    return '%s.%s@%s.sourceforge.net' % (nonce(40),
                                         c.app.config.options['mount_point'],
                                         '.'.join(reversed(parts)))

class ArtifactLink(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='artifact_link'
        indexes = [
            ('link', 'project_id') ]

    core_re = r'''\[
            (?:(?P<project_id>.*?):)?      # optional project ID
            (?:(?P<app_id>.*?):)?      # optional plugin ID
            (?P<artifact_id>.*)             # artifact ID
    \]'''

    re_link_1 = re.compile(r'\s' + core_re, re.VERBOSE)
    re_link_2 = re.compile(r'^' +  core_re, re.VERBOSE)

    _id = FieldProperty(str)
    link = FieldProperty(str)
    project_id = ForeignIdProperty('Project')
    plugin_name = FieldProperty(str)
    mount_point = FieldProperty(str)
    url = FieldProperty(str)

    @classmethod
    def add(cls, artifact):
        aid = artifact.index_id()
        entry = cls.query.get(_id=aid)
        if entry is None:
            entry = cls(_id=aid)
        entry.link=artifact.shorthand_id()
        entry.project_id=artifact.project_id
        entry.plugin_name=artifact.app_config.plugin_name
        entry.mount_point=artifact.app_config.options.mount_point
        entry.url=artifact.url()

    @classmethod
    def remove(cls, artifact):
        mapper(cls).remove(dict(_id=artifact.index_id()))

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
            projects = list(c.project.parent_iter())
        elif project_id.startswith('/'):
            projects = Project.query.find(dict(shortname=project_id[1:])).all()
        else:
            project_id = os.path.normpath(
                os.path.join('/' + c.project.shortname, project_id))
            projects = Project.query.find(dict(shortname=project_id[1:])).all()
        if not projects: return None
        #
        # Find the app_id to search
        #
        if app_id is None:
            app_id = c.app.config.options.mount_point
        #
        # Actually search the projects
        #
        with push_config(c, project=projects[0]):
            for p in projects:
                links = cls.query.find(dict(project_id=p._id, link=artifact_id)).all()
                for l in links:
                    if app_id == l.mount_point: return l
                for l in links:
                    if app_id == l.plugin_name: return l
        return None

class Artifact(MappedClass):
    class __mongometa__:
        session = artifact_orm_session
        name='artifact'
    type_s = 'Generic Artifact'

    # Artifact base schema
    _id = FieldProperty(S.ObjectId)
    app_config_id = ForeignIdProperty('AppConfig', if_missing=lambda:c.app.config._id)
    plugin_verson = FieldProperty(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.plugin_name:c.app.__version__})
    acl = FieldProperty({str:[S.ObjectId]})
    tags = FieldProperty([dict(tag=str, count=int)])
    app_config = RelationProperty('AppConfig')

    def dump_ref(self):
        '''Return a JSON-serializable reference to an artifact'''
        d = dict(project_id=self.app_config.project._id,
                    mount_point=self.app_config.options.mount_point,
                    artifact_type=pickle.dumps(self.__class__),
                    artifact_id=self._id)
        if isinstance(self._id, pymongo.bson.ObjectId):
            d['artifact_id'] = str(self._id)
        return d

    def dump_ref_str(self):
        '''Return a JSON-serializable reference to an artifact'''
        d = dict(project_id=str(self.app_config.project._id),
                    mount_point=self.app_config.options.mount_point,
                    artifact_type=pickle.dumps(self.__class__),
                    artifact_id=self._id)
        if isinstance(self._id, pymongo.bson.ObjectId):
            d['artifact_id'] = str(self._id)
        return d

    @classmethod
    def load_ref(cls,ref):
        from .project import Project
        project = Project.query.get(_id=pymongo.bson.ObjectId(ref['project_id']))
        with push_context(ref['project_id'], ref['mount_point']):
            acls = pickle.loads(ref['artifact_type'])
            obj = acls.query.get(_id=ref['artifact_id'])
            if obj is not None: return obj
            try:
                return acls.query.get(_id=pymongo.bson.ObjectId(str(ref['artifact_id'])))
            except:
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
        with push_config(c, project=project):
            project_role_id = user.project_role()._id
        for at in access_types:
            l = self.acl.setdefault(at, [])
            if project_role_id not in l:
                l.append(project_role_id)
            
    def revoke_access(self, *access_types, **kw):
        user = kw.pop('user', c.user)
        project = kw.pop('project', c.project)
        with push_config(c, project=project):
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
        return id

    def index(self):
        project = self.project
        return dict(
            id=self.index_id(),
            title_s='Artifact %s' % self._id,
            project_id_s=project._id,
            project_name_t=project.name,
            project_shortname_t=project.shortname,
            plugin_name_s=self.app_config.plugin_name,
            mount_point_s=self.app_config.options.mount_point,
            is_history_b=False,
            url_s=self.url(),
            type_s=self.type_s,
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

class Snapshot(Artifact):
    class __mongometa__:
        session = artifact_orm_session
        name='artifact_snapshot'

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
        result.update(
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

class Message(Artifact):
    class __mongometa__:
        session = artifact_orm_session
        name='message'
        indexes = [ 'slug', 'parent_id' ]

    _id=FieldProperty(str, if_missing=gen_message_id)
    slug=FieldProperty(str, if_missing=nonce)
    parent_id=FieldProperty(str)
    app_id=FieldProperty(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id=FieldProperty(S.ObjectId, if_missing=lambda:c.user._id)
    text=FieldProperty(str, if_missing='')

    def author(self):
        from .auth import User
        return User.query.get(_id=self.author_id) or User.anonymous

    def reply(self):
        new_id = gen_message_id()
        new_slug = self.slug + '/' + nonce()
        new_args = dict(
            state(self).document,
            _id=new_id,
            slug=new_slug,
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
            text=self.text,
            type_s='Generic Message')
        return result

    def shorthand_id(self):
        return self.slug

