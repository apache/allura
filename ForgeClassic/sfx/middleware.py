from sqlalchemy import Table, create_engine, select, func
from webob import exc, Request
from paste.deploy.converters import asint

from sf.phpsession import SFXSessionMgr

from allura.lib import helpers as h

from . import model as M

class SfxMiddleware(object):

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.environ_values = {
            'allura.sfx_session_manager': SFXSessionMgr(),
            }
        self.environ_values['allura.sfx_session_manager'].setup_sessiondb_connection_pool(
            config)
        self.configure_databases(config)

    def configure_databases(self, config):
        M.site_meta.bind = engine_from_config(h.config_with_prefix(config, 'site_db.'))
        M.mail_meta.bind = engine_from_config(h.config_with_prefix(config, 'mail_db.'))
        M.task_meta.bind = engine_from_config(h.config_with_prefix(config, 'task_db.'))
        M.epic_meta.bind = engine_from_config(h.config_with_prefix(config, 'epic_db.'))
        # Configure SFX Database Tables
        T = M.tables
        # Alexandria Tables
        T.mail_group_list = Table('mail_group_list', M.site_meta, autoload=True)
        T.groups = Table(
            'groups', M.site_meta, autoload=True,
            include_columns=['group_id', 'group_name', 'status'])
        T.mllist_subscriber = Table('mllist_subscriber', M.site_meta, autoload=True)
        T.prweb_vhost = Table('prweb_vhost', M.site_meta, autoload=True)
        T._mysql_auth = t = Table(
            'mysql_auth', M.site_meta, autoload=True,
            )
        T.mysql_auth = select([
            t,
            func.which_user(t.c.modified_by_uid).label('modified_user')]).alias('msql_auth_user')
        # MailDB tables
        T.lists = Table('lists', M.mail_meta, autoload=True)
        # TaskDB Tables
        T.ml_password_change = Table(
            'ml_password_change', M.task_meta, autoload=True)
        # EpicDB Tables
        T.backend_queue = Table('backend_queue', M.epic_meta, autoload=True)
        T.object_metadata = Table('object_metadata', M.epic_meta, autoload=True)
        T.feature_optin = Table('feature_optin', M.epic_meta, autoload=True)
        T.feature_grouping = Table('feature_grouping', M.epic_meta, autoload=True)
        T.sys_type_description = Table('sys_type_description', M.epic_meta, autoload=True)

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
