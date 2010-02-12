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

from pyforge.lib.helpers import push_config, set_context, encode_keys
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
    cloned_from = FieldProperty(str)
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

    def do_init(self, data, type):
        assert type in ["git", "svn", "hg"]
        self.type = type
        log.info(self.type + ' init')
        repo = c.app.repo
        scm = self.scmlib()
        cmd = scm.init()
        cmd.clean_dir()
        self.clear_commits()
        self.parent = None

        try:
            cmd.run_exc()
            repo_name = "/".join([c.project.shortname, c.app.config.options.mount_point])
            scm.setup_scmweb(repo_name, repo.repo_dir)
            scm.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
            repo.status = 'Ready'
        except AssertionError, ae:
            g.publish('react', 'error', dict(
                message=ae.args[0]))
            repo.status = 'Error: %s' % ae.args[0]
        except Exception, ex:
            g.publish('react', 'error', dict(message=str(ex)))
            repo.status = 'Error: %s' % ex


    def url(self):
        return self.app_config.url()

    def do_clone(self, url, type):
        """the separate method clone(), is called and run synchronously with the controller method, this method is the callback when the queued message is handled by the reactor"""
        assert type in ["git", "svn", "hg"]
        repo = c.app.repo
        log.info('Begin (%s) cloning %s', type, url)
        repo.type = type
        repo.clear_commits()
        scm = self.scmlib()
        repo.cloned_from = url

        cmd = None
        if type == "git":
            cmd = scm.clone(url, "tmp_dir")
        elif type == "hg":
            cmd = scm.clone(url, ".")
        elif type == "svn":
            # yipes: svn is ugly and requires
            # multiple cmds... so we do
            # this ugliness unlike git & hg
            try:
                scm.svn_clone(url)
            except Exception, ex:
                g.publish(
                        'react',
                        'error',
                        dict(message=str(ex)))
                repo.status = 'Error: %s' % ex
                return # don't continue after error

        if cmd:
            cmd.clean_dir()
            cmd.run()
        repo_name = "/".join([c.project.shortname, c.app.config.options.mount_point])
        log.info(scm)
        scm.setup_scmweb(repo_name, repo.repo_dir)
        scm.setup_commit_hook(repo.repo_dir, c.app.config.script_name()[1:])
        log.info('Clone complete for %s', url)
        if cmd and cmd.sp.returncode:
            errmsg = cmd.output
            g.publish('react', 'error', dict(message=errmsg))
            repo.status = 'Error: %s' % errmsg
        else:
            g.publish('react', 'scm.cloned', dict(
                    url=url))

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
            return self.repo_dir
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

    def scmweb_log_url(self):
        return self.native_url() + '?p=%s;a=log' % self.app.config.options.mount_point;

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

    # copied from git_react and hg_react
    def do_fork(self, data):
        log.info('Begin forking %s => %s', data['forked_from'], data['forked_to'])
        dest_project = Project.query.get(_id=bson.ObjectId(data['forked_to']['project_id']))
        data['forked_to']['project_shortname']=dest_project.shortname
        del data['forked_to']['project_id']
        src_project = Project.query.get(_id=bson.ObjectId(data['forked_from']['project_id']))
        data['forked_from']['project_shortname']=src_project.shortname
        del data['forked_from']['project_id']

        set_context(**encode_keys(data['forked_to']))

        # Set repo metadata
        dest_repo = c.app.repo

        # Perform the clone
        scm = self.scmlib()
        dest_repo.forked_from.update(data['forked_from'])
        log.info('Cloning from %s', data['url'])
        assert data['url'] == self.repo_dir

        if self.type == "git":
            cmd = scm.clone(self.repo_dir, "tmp_dir")
        elif self.type == "hg":
            cmd = scm.clone(self.repo_dir, '.')
        else:
            assert False # only git and hg supported
        cmd.clean_dir()
        dest_repo.clear_commits()
        cmd.run()
        dest_repo.status = 'Ready'
        log.info('Clone complete for %s', data['url'])
        repo_name = "/".join([dest_project.shortname, c.app.config.options.mount_point])
        scm.setup_scmweb(repo_name, dest_repo.repo_dir)

        scm.setup_commit_hook(dest_repo.repo_dir, c.app.config.script_name()[1:])
        if cmd.sp.returncode:
            errmsg = cmd.output
            g.publish('react', 'error', dict(
                    message=errmsg))
            dest_repo.status = 'Error: %s' % errmsg
            return
        else:
            log.info("Sending scm.forked message")
            g.publish('react', 'scm.forked', data)



    def fork(self, project_id, mount_point):
        """create a fork from an existing openforge repository"""
        clone_url = self.clone_url()
        p = Project.query.get(_id=bson.ObjectId(str(project_id)))
        app = p.install_app('Repository', mount_point,
                            type=c.app.config.options.type)
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.type = app.repo.type
            repo.status = 'pending fork'
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
        return "%s?p=%s;a=commit;h=%s" % (
                self.repository.native_url(),
                self.repository.app.config.options.mount_point,
                self.hash)

MappedClass.compile_all()
