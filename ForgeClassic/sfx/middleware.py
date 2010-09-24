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
        configure_databases(config)

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

def configure_databases(config):
    M.site_meta.bind = engine_from_config(h.config_with_prefix(config, 'site_db.'))
    M.mail_meta.bind = engine_from_config(h.config_with_prefix(config, 'mail_db.'))
    M.task_meta.bind = engine_from_config(h.config_with_prefix(config, 'task_db.'))
    M.epic_meta.bind = engine_from_config(h.config_with_prefix(config, 'epic_db.'))
    # Configure SFX Database Tables
    T = M.tables
    # Alexandria Tables
    T.mail_group_list = Table('mail_group_list', M.site_meta, autoload=True)
    T.users = Table(
        'users', M.site_meta, autoload=True,
        include_columns=[
            u'user_id', u'user_name', u'email', u'user_pw', u'realname',
            u'status', u'shell', u'unix_pw', u'unix_status', u'unix_uid',
            u'unix_box', u'add_date', u'confirm_hash', u'mail_siteupdates',
            u'mail_va', u'email_new', u'people_view_skills', u'people_resume',
            u'timezone', u'language', u'block_ratings', u'lastip',
            u'lastuseragent', u'lasttime', u'cf_uid', u'stay_anon',
            u'donation_request', u'donate_optin', u'paypal_id',
            u'last_sitestatus_view', u'is_subscribed', u'icon_data',
            u'hash_timeout', u'row_modtime', u'unsub_hash',
            u'user_pw_modtime', u'true_identity', u'openid_default' ])
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
    T.trove_cat = Table('trove_cat', M.site_meta, autoload=True)
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
