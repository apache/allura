from tg import expose
from pylons import c, g

from pyforge import app
from pyforge import model as M
from pyforge.lib import app_globals
from pyforge.lib.base import BaseController

class WSGIHook(app.WSGIHook, BaseController):

    def handles(self, environ):
        prefix = '/_wsgi_/scm'
        if environ['PATH_INFO'].startswith(prefix+ '/'):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(prefix):]
            environ['SCRIPT_NAME'] = prefix
            return True

    def __call__(self, environ, start_response):
        url_path = environ['PATH_INFO'][1:].split('/')
        project_id = '/'.join(url_path[:-1]) + '/'
        class EmptyClass(object): pass
        c.project = M.Project.m.get(_id=project_id)
        c.app = c.project.app_instance(url_path[-1])
        environ['PATH_INFO'] = '/'
        return BaseController.__call__(self, environ, start_response)

    @expose()
    def index(self):
        return '''
        Porject = %s, App = %s
        ''' % (c.project, c.app)

    
