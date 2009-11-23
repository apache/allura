from tg import expose, redirect, flash
from pylons import c

from pyforge.lib.security import require_forge_access

class ConfigOption(object):

    def __init__(self, name, ming_type, default):
        self.name, self.ming_type, self._default = (
            name, ming_type, default)

    @property
    def default(self):
        if callable(self._default):
            return self._default()
        return self._default

class Application(object):
    'base pyforge pluggable application'
    __version__ = None
    config_options = [
        ConfigOption('mount_point', str, 'app') ]
    templates=None # path to templates
    script_name=None
    root=None  # root controller
    permissions=[]

    def __init__(self, project, app_config_object):
        self.project = project
        self.config = app_config_object # pragma: no cover
        self.admin = DefaultAdminController()
        self.script_name = project.script_name + self.config.options.mount_point

    @classmethod
    def default_options(cls):
        return dict(
            (co.name, co.default)
            for co in cls.config_options)

    def install(self, project):
        'Whatever logic is required to initially set up a plugin'
        pass # pragma: no cover

    def uninstall(self, project):
        'Whatever logic is required to tear down a plugin'
        pass # pragma: no cover

class DefaultAdminController(object):

    @expose('pyforge.templates.app_admin')
    def index(self):
        return dict()

    @expose()
    def configure(self, **kw):
        require_forge_access(c.project, 'plugin')
        is_admin = c.app.config.plugin_name == 'admin'
        if kw.pop('delete', False):
            if is_admin:
                flash('Cannot delete the admin plugin, sorry....')
                redirect('.')
            c.project.uninstall_app(c.app.config.options.mount_point)
            redirect('..')
        for k,v in kw.iteritems():
            c.app.config.options[k] = v
        c.app.config.m.save()
        if is_admin:
            # possibly moving admin mount point
            redirect('/'
                     + c.project._id
                     + c.app.config.options.mount_point
                     + '/'
                     + c.app.config.options.mount_point
                     + '/')
        else:
            redirect('../' + c.app.config.options.mount_point + '/')

    @expose()
    def add_perm(self, permission, role):
        c.app.config.acl[permission].append(role)
        c.app.config.m.save()
        redirect('.#app-acl')

    @expose()
    def del_perm(self, permission, role):
        c.app.config.acl[permission].remove(role)
        c.app.config.m.save()
        redirect('.#app-acl')
        

