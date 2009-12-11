from datetime import datetime

from pylons import c, g
from pymongo.errors import OperationFailure

from ming import Field, schema
from pyforge.model import Project, Artifact, VersionedArtifact, Snapshot, Message

class Repository(Artifact):
    class __mongometa__:
        name='repository'
    type_s = 'ForgeSCM Repository'

    _id = Field(schema.ObjectId)
    description = Field(str)
    status = Field(str)
    parent = Field(str)

    def url(self):
        return c.app.script_name + '/repo/'

    def native_url(self):
        return '/_wsgi_/scm/' + c.app.script_name

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='%s repository' % c.app.script_name,
            type_s=self.type_s,
            text=self.description)
        return result

    def commits(self):
        return Commit.m.find(dict(repository_id=self._id))

    def clear_commits(self):
        Patch.m.remove(dict(repository_id=self._id))
        Commit.m.remove(dict(repository_id=self._id))

    def fork(self, project_id, mount_point):
        p = Project.m.get(_id=project_id)
        p.install_app('Repository', mount_point)
        new_app = p.app_instance(mount_point)
        new_app.repo.status = 'Pending Fork'
        g.publish('audit', 'scm.%s.fork' % c.app.config.options.type,
                  target=dict(project_id=project_id,
                              mount_point=mount_point))

class Commit(Artifact):
    class __mongometa__:
        name='commit'
    type_s = 'ForgeSCM Commit'

    _id = Field(schema.ObjectId)
    hash = Field(str)
    repository_id = Field(schema.ObjectId)
    summary = Field(str)
    diff = Field(str)
    date = Field(str)
    parents = Field([str])
    tags = Field([str])
    user = Field(str)
    branch = Field(str)

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='Commit %s by %s' % (self.hash, self.user),
            text=self.summary)
        return result

    @property
    def repository(self):
        return Repository.m.get(_id=self.repository_id)

    @property
    def patches(self):
        return Patch.m.find(dict(commit_id=self._id))

    def url(self):
        return self.repository.url() + self.hash + '/'

class Patch(Artifact):
    class __mongometa__:
        name='diff'
    type_s = 'ForgeSCM Patch'

    _id = Field(schema.ObjectId)
    repository_id = Field(schema.ObjectId)
    commit_id = Field(schema.ObjectId)
    filename = Field(str)
    patch_text = Field(schema.Binary)

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='Commit %s: %s' % (self.commit.hash, self.filename),
            text=self.patch_text)
        return result
            
        
    @property
    def commit(self):
        return Commit.m.get(_id=self.commit_id)
        
    def url(self):
        return self.commit.url() + self._id.url_encode() + '/'

