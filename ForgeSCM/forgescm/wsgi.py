import os
import logging
import pkg_resources

import pylons
import paste.cgiapp
from tg import config
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
    def __init__(self):
        self.hg_ui = u = ui.ui()
        u.setconfig('web', 'style', 'gitweb')
        self._git_app = paste.cgiapp.CGIApplication(
            {}, config.get('gitweb.cgi', '/usr/lib/cgi-bin/gitweb.cgi'))

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
        elif c.app.config.options.type == 'git':
            return self.git_app(environ, start_response)
        elif c.app.config.options.type == 'svn':
            return self.hgweb_svn(environ, start_response)
        return BaseController.__call__(self, environ, start_response)

    def hgweb(self, environ, start_response):
        repo = c.app.repo.repo_dir
        name = 'Main Repository for %s' % c.project._id
        repo = hg.repository(self.hg_ui, repo)
        svr = hgweb(repo, name)
        return svr(environ, start_response)

    def hgweb_svn(self, environ, start_response):
        repo = c.app.repo.repo_dir + '/hg_repo'
        name = 'Main Repository for %s' % c.project._id
        repo = hg.repository(self.hg_ui, repo)
        svr = hgweb(repo, name)
        return svr(environ, start_response)

    def git_app(self, environ, start_response):
        environ['GITWEB_CONFIG_SYSTEM'] = str(
            c.app.repo.repo_dir + '/gitweb.conf')
        return self._git_app(environ, start_response)

    def find_project(self, url_path):
        length = len(url_path)
        while length:
            id = '/'.join(url_path[:length]) + '/'
            p = M.Project.query.get(_id=id)
            if p: return p, url_path[length:]
            length -= 1
        return None, url_path
    
