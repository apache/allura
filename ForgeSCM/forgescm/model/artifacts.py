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
                project_id=str,
                app_config_id=schema.ObjectId(if_missing=None))])
    forked_from = FieldProperty(dict(
            project_id=str,
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
            title_s='%s repository' % self.app_config.script_name(),
            text=self.description)
        return result

    def clear_commits(self):
        mapper(Patch).remove(dict(repository_id=self._id))
        mapper(Commit).remove(dict(repository_id=self._id))

    def fork_urls(self):
        for f in self.forks:
            with self.context_of(f) as repo:
                if repo:
                    yield repo.url()

    def fork(self, project_id, mount_point):
        clone_url = self.clone_url()
        forked_from = dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id)
        p = Project.query.get(_id=project_id)
        app = p.install_app('Repository', mount_point,
                            type=c.app.config.options.type)
        with push_config(c, project=p, app=app):
            repo = app.repo
            repo.type = app.repo.type
            repo.status = 'Pending Fork'
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
            log.exception('Error deleting %s', self.repo_dir)
        Artifact.delete(self)
        mapper(Commit).remove(dict(app_config_id=self.app_config_id))
        mapper(Patch).remove(dict(app_config_id=self.app_config_id))

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
    patches = RelationProperty('Patch', via='commit_id')

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

class Patch(Artifact):
    class __mongometa__:
        name='diff'
    type_s = 'ForgeSCM Patch'

    _id = FieldProperty(schema.ObjectId)
    repository_id = ForeignIdProperty(Repository)
    commit_id = ForeignIdProperty(Commit)
    filename = FieldProperty(str)
    patch_text = FieldProperty(schema.Binary)

    repository = RelationProperty(Repository, via='repository_id')
    commit = RelationProperty(Commit, via='commit_id')

    def _get_unicode_text(self):
        '''determine the encoding and return either unicode or u"<<binary data>>"'''
        if not self.patch_text: return u''
        for attempt in ('ascii', 'utf-8', 'latin-1'):
            try:
                return unicode(self.patch_text, attempt)
            except UnicodeDecodeError:
                pass
        encoding = chardet.detect(self.patch_text)
        if encoding['confidence'] > 0.6:
            return unicode(self.patch_text, encoding['encoding'])
        else:
            return u'<<binary data>>'

    def index(self):
        result = Artifact.index(self)
        if self.patch_text:
            encoding = chardet.detect(self.patch_text)
            if encoding['confidence'] > 0.6:
                text = unicode(self.patch_text, encoding['encoding'])
            else:
                text = '<<binary data>'
        else:
            self.patch_Text = ''
        result.update(
            title_s='Patch on Commit %s: %s' % (self.commit.hash, self.filename),
            text=self._get_unicode_text())
        return result
            
    def shorthand_id(self):
        return self.commit.shorthand_id() + '.' + self.filename
        
    def url(self):
        try:
            return self.commit.url() + self._id.url_encode() + '/'
        except:
            log.exception("Cannot get patch URL")
            return '#'

MappedClass.compile_all()
