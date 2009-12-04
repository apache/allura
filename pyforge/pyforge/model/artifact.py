import re
import os
from time import sleep
from datetime import datetime
from hashlib import sha1

import pymongo
from pylons import c
from ming import Document, Session, Field
from ming import schema as S
from pymongo.bson import ObjectId
from pymongo.errors import OperationFailure

from .session import ProjectSession

from pyforge.lib import search

def nonce(length=4):
    return sha1(ObjectId().binary).hexdigest()[:4]

class ArtifactSession(ProjectSession):

    def remove(self, cls, *args, **kwargs):
        for a in self.find(cls, *args, **kwargs):
            search.remove_artifact(a)
            ArtifactLink.remove(a)
        ProjectSession.remove(self, cls, *args, **kwargs)

    def update_partial(self, cls, spec, fields, upsert):
        ProjectSession.update_partial(self, cls, spec, fields, upsert)
        for a in self.find(cls, spec):
            search.add_artifact(a)
            ArtifactLink.add(a)

    def save(self, doc, *args):
        ProjectSession.save(self, doc, *args)
        search.add_artifact(doc)
        ArtifactLink.add(doc)

    def insert(self, doc):
        ProjectSession.insert(self, doc)
        search.add_artifact(doc)
        ArtifactLink.add(doc)

    def update(self, doc, spec, upsert=False):
        ProjectSession.update(self, doc, spec, upsert)
        search.add_artifact(doc)
        ArtifactLink.add(doc)

    def delete(self, doc):
        ProjectSession.delete(self, doc)
        search.remove_artifact(doc)
        ArtifactLink.remove(doc)

    def set(self, doc, fields_values):
        ProjectSession.set(self, doc, fields_values)
        search.add_artifact(doc)
        ArtifactLink.add(doc)

    def increase_field(self, doc, **kwargs):
        ProjectSession.increase_field(self, doc, **kwargs)
        search.add_artifact(doc)
        ArtifactLink.add(doc)

class ArtifactLink(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='artifact_link'
        indexes = [
            ('link', 'project_id') ]

    re_link = re.compile('''\[
        (?:(.*?):)?      # optional project ID
        (?:(.*?):)?      # optional plugin ID
        (.*)             # artifact ID
        \]''', re.VERBOSE)

    _id = Field(str)
    link = Field(str)
    project_id = Field(str)
    plugin_name = Field(str)
    mount_point = Field(str)
    url = Field(str)

    @classmethod
    def add(cls, artifact):
        entry = cls.make(dict(
                _id=artifact.index_id(),
                link=artifact.shorthand_id(),
                project_id=artifact.project._id,
                plugin_name=c.app.config.plugin_name,
                mount_point=c.app.config.options.mount_point,
                url=artifact.url()))
        entry.m.save()

    @classmethod
    def remove(cls, artifact):
        cls.m.remove(dict(_id=artifact.index_id()))

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
            projects = Project.m.find(dict(_id=project_id[1:] + '/')).all()
        else:
            project_id = os.path.normpath(
                os.path.join('/' + c.project._id[:-1], project_id))
            projects = Project.m.find(dict(_id=project_id[1:] + '/')).all()
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
                links = cls.m.find(dict(project_id=p._id, link=artifact_id)).all()
                for l in links:
                    if app_id == l.mount_point: return l
                for l in links:
                    if app_id == l.plugin_name: return l
        return None

class Artifact(Document):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='artifact'

    # Artifact base schema
    _id = Field(S.ObjectId)
    app_config_id = Field(S.ObjectId, if_missing=lambda:c.app.config._id)
    plugin_verson = Field(
        S.Object,
        { str: str },
        if_missing=lambda:{c.app.config.plugin_name:c.app.__version__})
    acl = Field({str:[S.ObjectId]})

    @property
    def app_config(self):
        from .project import AppConfig
        return AppConfig.m.get(_id=self.app_config_id)

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
            type_s='Generic Artifact')

    def url(self):
        raise NotImplementedError, 'url'

    def shorthand_id(self):
        '''How to refer to this artifact within the app instance context.

        For a wiki page, it might be the title.  For a ticket, it might be the
        ticket number.  For a discussion, it might be the message ID.  Generally
        this should have a strong correlation to the URL.
        '''
        raise NotImplementedError, 'shorthand_id'
        

class Snapshot(Artifact):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='artifact_snapshot'

    _id = Field(S.ObjectId)
    artifact_id = Field(S.ObjectId)
    artifact_class = Field(str)
    version = Field(S.Int, if_missing=0)
    author = Field(dict(
            id=S.ObjectId,
            username=str,
            display_name=str))
    timestamp = Field(datetime)
    data = Field(None)

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

class VersionedArtifact(Artifact):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='versioned_artifact'
        history_class = Snapshot

    version = Field(S.Int, if_missing=0)

    def commit(self):
        '''Save off a snapshot of the artifact as well as saving the
        artifact itself.'''
        self.m.save()
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
            data=self)
        ss = self.__mongometa__.history_class.make(data)
        ss.m.save()
        return ss

    def get_version(self, n):
        if n < 0:
            n = self.version + n + 1
        ss = self.__mongometa__.history_class.m.get(
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
        q = HC.m.find(dict(artifact_id=self._id)).sort('version', pymongo.DESCENDING)
        return q

class Message(Artifact):
    class __mongometa__:
        session = ArtifactSession(Session.by_name('main'))
        name='message'

    _id=Field(str, if_missing=nonce)
    parent_id=Field(str)
    app_id=Field(S.ObjectId, if_missing=lambda:c.app.config._id)
    timestamp=Field(datetime, if_missing=datetime.utcnow)
    author_id=Field(S.ObjectId, if_missing=lambda:c.user._id)
    text=Field(str, if_missing='')

    def author(self):
        from .auth import User
        return User.m.get(_id=self.author_id) or User.anonymous

    def reply(self):
        while True:
            try:
                new_id = self._id + '/' + nonce()
                msg = self.make(dict(
                        self,
                        _id=new_id,
                        parent_id=self._id,
                        timestamp=datetime.utcnow(),
                        author_id=c.user._id))
                msg.m.insert()
                return msg
            except OperationFailure:
                sleep(0.1)
                continue # pragma: no cover

    def descendants(self):
        q = self.m.find(dict(_id={'$gt':self._id}))
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
