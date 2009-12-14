from tg import expose, flash, redirect, validate
from pylons import c, g
from formencode import validators
from pymongo import bson

from pyforge.lib import search

from forgescm import model

class RootController(object):

    def __init__(self):
        self.repo = CommitsController()

    @expose('forgescm.templates.index')
    def index(self):
        repo = c.app.repo
        return dict(repo=repo)

    @expose('forgescm.templates.fork')
    def fork(self, project, mount_point):
        repo = c.app.repo
        new_url = repo.fork(project, mount_point)
        flash('Project %s forked' % repo.url())
        redirect(new_url)
                    
                  
    @expose('forgescm.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local plugin search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND mount_point_s:%s''' % (
                q, history, c.app.config.options.mount_point)
            results = search.search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose()
    def reinit(self):
        repo = c.app.repo
        repo.status = 'Pending Reinit'
        repo.m.save()
        g.publish('audit', 'scm.%s.init' % c.app.config.options.type, {})
        redirect('.')
        
    @expose()
    def reclone(self):
        repo = c.app.repo
        repo.status = 'Pending Reclone'
        repo.m.save()
        g.publish('audit', 'scm.%s.reclone' % c.app.config.options.type, {})
        redirect('.')
        
    @expose()
    def clone_from(self, url=None):
        repo = c.app.repo
        repo.status = 'Pending Clone'
        repo.m.save()
        g.publish('audit', 'scm.%s.clone' % c.app.config.options.type, dict(
                url=url))
        redirect('.')

    @expose()
    def pull_request(self):
        repo = c.app.repo
        url = repo.url()
        clone_url = repo.clone_url()
        with repo.context_of(repo.forked_from):
            repo = c.app.repo
            repo.pull_requests.append(
                'Pull request from <a href="%s">%s</a> (%s)' % (url, url, clone_url))
            repo.m.save()
        flash('Pull request sent')
        redirect('.')

    @expose()
    def delete_pull_request(self, i):
        repo = c.app.repo
        del repo.pull_requests[int(i)]
        repo.m.save()
        redirect('.')

class CommitsController(object):

    def _lookup(self, id, *remainder):
        if ':' in id: id = id.split(':')[-1]
        if '%3A' in id: id = id.split('%3A')[-1]
        return CommitController(id), remainder

class CommitController(object):

    def __init__(self, id):
        self.commit = model.Commit.m.get(hash=id)

    @expose('forgescm.templates.commit_index')
    def index(self):
        return dict(value=self.commit)

    def _lookup(self, id, *remainder):
        return PatchController(id), remainder

class PatchController(object):

    def __init__(self, id):
        self.patch = model.Patch.m.get(_id=bson.ObjectId.url_decode(id))

    @expose('forgescm.templates.patch_index')
    def index(self):
        return dict(value=self.patch)
