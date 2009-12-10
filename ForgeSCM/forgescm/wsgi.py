import logging

from tg import expose
from pylons import c, g
from mercurial import ui, hg
from mercurial.hgweb import hgweb

from pyforge import app
from pyforge import model as M
from pyforge.lib import app_globals
from pyforge.lib.base import BaseController

log = logging.getLogger(__name__)

class WSGIHook(app.WSGIHook, BaseController):
    '''
    Handle URLs like /_wsgi_/scm/proj/subproj/subsub/src/...
    '''

    def handles(self, environ):
        prefix = '/_wsgi_/scm'
        if environ['PATH_INFO'].startswith(prefix+ '/'):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(prefix):]
            environ['SCRIPT_NAME'] = prefix
            return True

    def __call__(self, environ, start_response):
        url_path = environ['PATH_INFO'][1:].split('/')
        project, rest = self.find_project(url_path)
        if project is None:
            return BaseController.__call__(self, environ, start_response)
        class EmptyClass(object): pass
        c.project = project
        c.app = c.project.app_instance(rest[0])
        environ['PATH_INFO'] = '/' + '/'.join(rest[1:])
        environ['SCRIPT_NAME'] += '/' + c.project._id + rest[0]
        if c.app.config.options.type == 'hg':
            return self.hgweb(environ, start_response)
        return BaseController.__call__(self, environ, start_response)

    def hgweb(self, environ, start_response):
        repo = c.app.repo_dir
        name = 'Main Repository for %s' % c.project._id
        log.info('About to serve %s from %s', name, repo)
        repo = hg.repository(ui.ui(), repo)
        svr = hgweb(repo, name)
        log.info('Server created')
        return svr(environ, start_response)

    def find_project(self, url_path):
        length = len(url_path)
        while length:
            id = '/'.join(url_path[:length]) + '/'
            p = M.Project.m.get(_id=id)
            if p: return p, url_path[length:]
            length -= 1
        return None, url_path
    
