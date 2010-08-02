from sqlalchemy import Table, create_engine
from webob import exc, Request
from paste.deploy.converters import asint

from sf.phpsession import SFXSessionMgr

from pyforge.lib import helpers as h

from . import model as M

class SfxMiddleware(object):

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.environ_values = {
            'allura.sfx_session_manager': SFXSessionMgr(),
            'allura.sfx.site_db':engine_from_config(h.config_with_prefix(config, 'site_db.')),
            'allura.sfx.mail_db':engine_from_config(h.config_with_prefix(config, 'mail_db.')),
            'allura.sfx.task_db':engine_from_config(h.config_with_prefix(config, 'task_db.')),
            'allura.sfx.epic_db':engine_from_config(h.config_with_prefix(config, 'epic_db.'))
            }
        self.environ_values['allura.sfx_session_manager'].setup_sessiondb_connection_pool(
            config)
        M.site_meta.bind = self.environ_values['allura.sfx.site_db']
        M.mail_meta.bind = self.environ_values['allura.sfx.mail_db']
        M.task_meta.bind = self.environ_values['allura.sfx.task_db']
        M.epic_meta.bind =self.environ_values['allura.sfx.epic_db']
        M.tables.mail_group_list = Table('mail_group_list', M.site_meta, autoload=True)
        M.tables.mllist_subscriber = Table('mllist_subscriber', M.site_meta, autoload=True)
        M.tables.backend_queue = Table('backend_queue', M.epic_meta, autoload=True)
        M.tables.lists = Table('lists', M.mail_meta, autoload=True)
        M.tables.ml_password_change = Table(
            'ml_password_change', M.task_meta, autoload=True)

    def __call__(self, environ, start_response):
        request = Request(environ)
        try:
            self.handle(request)
        except exc.HTTPException, resp:
            return resp(environ, start_response)
        resp = request.get_response(self.app)
        return resp(environ, start_response)

    def handle(self, request):
        request.environ.update(self.environ_values)

def engine_from_config(config):
    sa_scheme = config['scheme']
    sa_user = config['username']
    sa_password = config['password']
    sa_host = config['host']
    db = config['database']
    db_recycle = asint(config['pool_recycle'])
    db_size = asint(config['pool_size'])
    db_overflow = asint(config['pool_max_overflow'])
    sa_port = config.get('port', '')
    if sa_port: sa_port = ':' + sa_port
    return create_engine(
        '%s://%s:%s@%s%s/%s' % (sa_scheme, sa_user,sa_password,sa_host,sa_port,db),
        pool_recycle=db_recycle,
        pool_size=db_size,
        max_overflow=db_overflow,
        )
