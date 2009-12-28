import re
import os
import logging
from time import sleep
from datetime import datetime
from hashlib import sha1

import pymongo
from pylons import c
from ming import Document, Session, Field
from ming import schema as S
from ming.orm.base import mapper, session, state
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, ForeignIdProperty, RelationProperty
from pymongo.bson import ObjectId
from pymongo.errors import OperationFailure

from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session

log = logging.getLogger(__name__)

def nonce(length=4):
    return sha1(ObjectId().binary).hexdigest()[:4]

class ArtifactLink(MappedClass):
    class __mongometa__:
        session = project_orm_session
        name='artifact_link'
        indexes = [
            ('link', 'project_id') ]

    core_re = r'''\[
            (?:(.*?):)?      # optional project ID
            (?:(.*?):)?      # optional plugin ID
            (.*)             # artifact ID
    \]'''

    re_link = re.compile(r'(?:\s%s)|(?:^%s)' % (core_re, core_re),
                         re.VERBOSE)

    _id = FieldProperty(str)
    link = FieldProperty(str)
    project_id = FieldProperty(str)
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
        entry.project_id=artifact.project._id
        entry.plugin_name=artifact.app_config.plugin_name
        entry.mount_point=artifact.app_config.options.mount_point
        entry.url=artifact.url()

    @classmethod
    def remove(cls, artifact):
        mapper(cls).remove(dict(_id=artifact.index_id()))

    @classmethod
    def lookup(cls, link):
        from .project import Project
        from pyforge.lib.helpers import push_config
        #
        # Parse the link syntax
        #
        m = cls.re_link.match(link)
        if m is None: return None
        groups = m.groups()
        if groups[1] is None:
            # foo:bar comes in as (foo, None, bar), so make it (None, foo, bar)
            groups = groups[1], groups[0], groups[2]
        project_id, app_id, artifact_id = groups
        #
        # Find the projects to search
        #
        if project_id is None:
            projects = list(c.project.parent_iter())
        elif project_id.startswith('/'):
            projects = Project.query.find(dict(_id=project_id[1:] + '/')).all()
        else:
            project_id = os.path.normpath(
                os.path.join('/' + c.project._id[:-1], project_id))
            projects = Project.query.find(dict(_id=project_id[1:] + '/')).all()
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
    app_config = RelationProperty('AppConfig')

    @property
    def project(self):
        return self.app_config.project

    @property
    def app(self):
        ac = self.app_config
        return self.app_config.load()(self.project, self.app_config)

    def index_id(self):
        id = '%s.%s#%s' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._id)
        return id

    def index(self):
        project = self.project
        if project is None:
            import pdb; pdb.set_trace()
        if hasattr(self._id, 'url_encode'):
            _id = self._id.url_encode()
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
        raise NotImplementedError, 'url'

    def shorthand_id(self):
        '''How to refer to this artifact within the app instance context.

        For a wiki page, it might be the title.  For a ticket, it might be the
        ticket number.  For a discussion, it might be the message ID.  Generally
        this should have a strong correlation to the URL.
        '''
        return self._id.url_encode() # for those who like PAIN

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
        raise NotImplemented, 'original'
            
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
        self.update(version.data)
        self.version = old_version

    def history(self):
        HC = self.__mongometa__.history_class
        q = HC.query.find(dict(artifact_id=self._id)).sort('version', pymongo.DESCENDING)
        return q

class Message(Artifact):
    class __mongometa__:
        session = artifact_orm_session
        name='message'

    _id=FieldProperty(str, if_missing=nonce)
    parent_id=FieldProperty(str)
    app_id=FieldProperty(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id=FieldProperty(S.ObjectId, if_missing=lambda:c.user._id)
    text=FieldProperty(str, if_missing='')

    def author(self):
        from .auth import User
        return User.query.get(_id=self.author_id) or User.anonymous

    def reply(self):
        while True:
            try:
                new_id = self._id + '/' + nonce()
                new_args = dict(
                    state(self).document,
                    _id=new_id,
                    parent_id=self._id,
                    timestamp=datetime.utcnow(),
                    author_id=c.user._id)
                msg = self.__class__(**new_args)
                return msg
            except OperationFailure:
                sleep(0.1)
                continue # pragma: no cover

    def descendants(self):
        q = self.query.find(dict(_id={'$gt':self._id}))
        for msg in q:
            if msg._id.startswith(self._id):
                yield msg
            else:
                break

    def replies(self):
        depth = self._id.count('/')
        for msg in self.descendants():
            if msg._id.count('/') - depth == 1:
                yield msg

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
        return self._id
        return '%s#%s' % (self.original().shorthand_id(), self.version)

