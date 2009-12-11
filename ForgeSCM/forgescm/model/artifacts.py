import os
import shutil
import logging
from datetime import datetime
from contextlib import contextmanager

from tg import config
from pylons import c, g
from pymongo.errors import OperationFailure

from ming import Field, schema
from pyforge.lib.helpers import push_config
from pyforge.model import Project, Artifact, AppConfig

log = logging.getLogger(__name__)

class Repository(Artifact):
    class __mongometa__:
        name='repository'
    type_s = 'ForgeSCM Repository'

    _id = Field(schema.ObjectId)
    description = Field(str)
    status = Field(str)
    parent = Field(str)
    type = Field(str, if_missing='hg')
    pull_requests = Field([str])
    repo_dir = Field(str)
    forks = Field([dict(
                project_id=str,
                app_config_id=schema.ObjectId(if_missing=None))])
    forked_from = Field(dict(
            project_id=str,
            app_config_id=schema.ObjectId(if_missing=None)))

    def url(self):
        return c.app.script_name + '/'

    def clone_command(self):
        if self.type == 'hg':
            return 'hg clone ' + self.clone_url()
        return '<unknown command>'

    def clone_url(self):
        return config.get('host_prefix', 'http://localhost:8080') + self.native_url()

    def native_url(self):
        return '/_wsgi_/scm' + c.app.script_name

    def file_browser(self):
        return self.native_url() + '/file'

    def forked_from_url(self):
        with self.context_of(self.forked_from) as repo:
            return repo.url()

    def forked_from_repo(self):
        with self.context_of(self.forked_from) as repo:
            return repo

    @classmethod
    @contextmanager
    def context_of(cls, repo_info):
        p = Project.m.get(_id=repo_info.project_id)
        with push_config(c, project=p):
            app_config = AppConfig.m.get(_id=repo_info.app_config_id)
            app = p.app_instance(app_config)
            with push_config(c, app=app):
                yield app.repo

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

    def fork_urls(self):
        for f in self.forks:
            with self.context_of(f) as repo:
                yield repo.url()

    def fork(self, project_id, mount_point):
        clone_url = self.clone_url()
        forked_from = dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id)
        p = Project.m.get(_id=project_id)
        app = p.install_app('Repository', mount_point)
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.status = 'Pending Fork'
            repo.m.save()
            new_url = repo.url()
        g.publish('audit', 'scm.%s.fork' % c.app.config.options.type, dict(
                url=clone_url,
                forked_to=dict(project_id=project_id,
                               app_config_id=app.config._id.url_encode()),
                forked_from=dict(project_id=c.project._id,
                                 app_config_id=c.app.config._id.url_encode())))
        return new_url

    def delete(self):
        try:
            if os.path.exists(self.repo_dir):
                shutil.rmtree(self.repo_dir)
        except:
            log.exception('Error deleting %s', self.repo_dir_)
        self.m.delete()
        Commit.m.remove(dict(app_config_id=self.app_config_id))
        Patch.m.remove(dict(app_config_id=self.app_config_id))

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

    def shorthand_id(self):
        return self.hash

    @property
    def repository(self):
        return Repository.m.get(_id=self.repository_id)

    @property
    def patches(self):
        return Patch.m.find(dict(commit_id=self._id))

    def url(self):
        return self.repository.url() + 'repo/' + self.hash + '/'

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
            
    def shorthand_id(self):
        return self.commit.shorthand_id() + '.' + self.filename
        
    @property
    def commit(self):
        return Commit.m.get(_id=self.commit_id)
        
    def url(self):
        try:
            return self.commit.url() + self._id.url_encode() + '/'
        except:
            log.exception("Cannot get patch URL")
            return '#'

