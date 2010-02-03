import os
import shutil
import logging
from datetime import datetime
from contextlib import contextmanager

from tg import config
import chardet
from pylons import c, g
import pymongo
from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.base import state, session, mapper
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from pyforge.lib.helpers import push_config
from pyforge.model import Project, Artifact, AppConfig
from pymongo import bson
import sys
import forgescm.lib

log = logging.getLogger(__name__)

class Repository(Artifact):
    class __mongometa__:
        name='repository'
    type_s = 'ForgeSCM Repository'

    _id = FieldProperty(schema.ObjectId)
    description = FieldProperty(str)
    status = FieldProperty(str)
    parent = FieldProperty(str)
    type = FieldProperty(str, if_missing='hg')
    pull_requests = FieldProperty([str])
    repo_dir = FieldProperty(str)
    forks = FieldProperty([dict(
                project_id=schema.ObjectId,
                app_config_id=schema.ObjectId(if_missing=None))])
    forked_from = FieldProperty(dict(
            project_id=schema.ObjectId,
            app_config_id=schema.ObjectId(if_missing=None)))

    commits = RelationProperty('Commit', via='repository_id',
                               fetch=False)

    def ordered_commits(self, limit=None):
        q = self.commits
        q = q.sort([('rev', pymongo.DESCENDING),
                    ('date', pymongo.DESCENDING)])
        if limit:
            q = q.limit(limit)
        return q

    def scmlib(self):
        if self.type == 'git':
            return forgescm.lib.git
        elif self.type == 'hg':
            return forgescm.lib.hg
        elif self.type == 'svn':
            return forgescm.lib.svn

    ## patterned after git_react/init...
    ## compare/make sure it does everything
    ## hg and svn init do
    def init(self, data):
        '''This is the fat model method to handle a reactor's init call'''
        log.info(self.type + ' init')
        print >> sys.stderr, self.type + ' init'
        repo = c.app.repo
        scm = self.scmlib()
        cmd = scm.init()
        cmd.clean_dir()
        self.clear_commits()
        self.parent = None
        cmd.run()
        log.info('Setup gitweb in %s', self.repo_dir)
        repo_name = c.project.shortname + c.app.config.options.mount_point
        scm.setup_scmweb(repo_name, repo.repo_dir)
        scm.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
        if cmd.sp.returncode:
            g.publish('react', 'error', dict(
                message=cmd.output))
            repo.status = 'Error: %s' % cmd.output
        else:
            repo.status = 'Ready'

    def url(self):
        return self.app_config.url()

    def clone_command(self):
        if self.type == 'hg':
            return 'hg clone ' + self.clone_url()
        elif self.type == 'git':
            return 'git clone ' + self.clone_url()
        elif self.type == 'svn':
            return 'svn co ' + self.clone_url()
        return '<unknown command>'

    def clone_url(self):
        if self.type == 'hg':
            return config.get('host_prefix', 'http://localhost:8080') \
                + self.native_url()
        elif self.type == 'git':
            return self.repo_dir
        elif self.type == 'svn':
            return 'file://' + self.repo_dir + '/svn_repo'
        else:
            return 'Unknown clone url'

    def native_url(self):
        # Still using script_name() because we need to make sure
        #  this is on the same host as the page is being served from
        return '/_wsgi_/scm' + self.app_config.script_name()

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
        p = Project.query.get(_id=repo_info['project_id'])
        with push_config(c, project=p):
            app_config = AppConfig.query.get(_id=repo_info['app_config_id'])
            if app_config: 
                app = p.app_instance(app_config)
                with push_config(c, app=app):
                    yield app.repo
            else:
                yield None

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='%s repository' % self.app_config.url(),
            text=self.description)
        return result

    def clear_commits(self):
        mapper(Commit).remove(dict(repository_id=self._id))

    def fork_urls(self):
        for f in self.forks:
            with self.context_of(f) as repo:
                if repo:
                    yield repo.url()

    def fork(self, project_id, mount_point):
        clone_url = self.clone_url()
        p = Project.query.get(_id=bson.ObjectId(str(project_id)))
        app = p.install_app('Repository', mount_point,
                            type=c.app.config.options.type)
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.type = app.repo.type
            repo.status = 'Pending Fork'
            new_url = repo.url()
        g.publish('audit', 'scm.%s.fork' % c.app.config.options.type, dict(
                url=clone_url,
                forked_to=dict(project_id=str(p._id),
                               app_config_id=str(app.config._id)),
                forked_from=dict(project_id=str(c.project._id),
                                 app_config_id=str(c.app.config._id))))
        return new_url

    def delete(self):
        try:
            if os.path.exists(self.repo_dir):
                shutil.rmtree(self.repo_dir)
        except:
            log.exception('Error deleting %s', self.repo_dir)
        Artifact.delete(self)
        mapper(Commit).remove(dict(app_config_id=self.app_config_id))

class Commit(Artifact):
    class __mongometa__:
        name='commit'
    type_s = 'ForgeSCM Commit'

    _id = FieldProperty(schema.ObjectId)
    hash = FieldProperty(str)
    rev = FieldProperty(int) # only relevant for hg and svn repos
    repository_id = ForeignIdProperty(Repository)
    summary = FieldProperty(str)
    diff = FieldProperty(str)
    date = FieldProperty(datetime)
    parents = FieldProperty([str])
    tags = FieldProperty([str])
    user = FieldProperty(str)
    branch = FieldProperty(str)

    repository = RelationProperty(Repository, via='repository_id')

    def index(self):
        result = Artifact.index(self)
        result.update(
            title_s='Commit %s by %s' % (self.hash, self.user),
            text=self.summary)
        return result

    def shorthand_id(self):
        return self.hash

    def url(self):
        return self.repository.url() + 'repo/' + self.hash + '/'


MappedClass.compile_all()
