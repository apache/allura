# -*- coding: utf-8 -*-
"""Setup the pyforge application"""
import os
import sys
import logging
import shutil
from datetime import datetime
from mimetypes import guess_type

from pylons import c, g
from paste.deploy.converters import asbool

from flyway.command import MigrateCommand
from flyway.model import MigrationInfo
from ming import Session, mim
from ming.orm.ormsession import ThreadLocalORMSession

import pyforge
from pyforge import model as M

log = logging.getLogger(__name__)

def set_flyway_info():
    versions = dict(
        pyforge=1,
        ForgeTracker=0,
        ForgeWiki=0)
    mi = MigrationInfo.make(dict(versions=versions))
    conn = M.main_doc_session.bind.conn
    for database in conn.database_names():
        log.info('Initialize Flyway for %s', database)
        session = DBSession(conn[database])
        session.insert(mi)

def cache_test_data():
    log.info('Saving data to cache in .test-data')
    if os.path.exists('.test-data'):
        shutil.rmtree('.test-data')
    os.system('mongodump -h 127.0.0.1:27018 -o .test-data > mongodump.log 2>&1')

def restore_test_data():
    if os.path.exists('.test-data'):
        log.info('Restoring data from cache in .test-data')
        rc = os.system('mongorestore -h 127.0.0.1:27018 --dir .test-data > mongorestore.log 2>&1')
        return rc == 0
    else:
        return False

def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""
    # Clean up all old stuff
    ThreadLocalORMSession.close_all()
    c.queued_messages = []
    c.user = c.project = c.app = None
    database=conf.get('db_prefix', '') + 'project:test'
    g._push_object(pyforge.lib.app_globals.Globals())
    wipe_database()
    try:
        g.solr.delete(q='*:*')
    except: # pragma no cover
        log.error('SOLR server is %s', g.solr_server)
        log.error('Error clearing solr index')
    if asbool(conf.get('cache_test_data')):
        if restore_test_data():
            c.project = M.Project.query.get(shortname='test')
            return
    log.info('Initializing search')
    M.SearchConfig(last_commit = datetime.utcnow(),
                   pending_commit = 0)
    g.publish('audit', 'search.check_commit', {})
    log.info('Registering initial users & neighborhoods')
    anonymous = M.User(_id=None,
                       username='*anonymous',
                       display_name='Anonymous Coward')
    root = create_user('Root')
    n_projects = M.Neighborhood(name='Projects',
                             url_prefix='/p/',
                             acl=dict(read=[None], create=[],
                                      moderate=[root._id], admin=[root._id]))
    n_users = M.Neighborhood(name='Users',
                             url_prefix='/u/',
                             shortname_prefix='u/',
                             acl=dict(read=[None], create=[],
                                      moderate=[root._id], admin=[root._id]))
    n_adobe = M.Neighborhood(name='Adobe',
                             url_prefix='/adobe/',
                             acl=dict(read=[None], create=[],
                                      moderate=[root._id], admin=[root._id]))
    M.Theme(name='forge_default',
            label='Default Forge Theme',
            color1='#0088cc',
            color2='#000000',
            color3='#454545',
            color4='#6c7681',
            color5='#d8d8d8',
            color6='#ececec')
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    # add the adobe icon
    file_name = 'adobe_icon.png'
    file_path = os.path.join(pyforge.__path__[0],'public','images',file_name)
    f = file(file_path, 'r')
    content_type = guess_type(file_name)
    if content_type: content_type = content_type[0]
    else: content_type = 'application/octet-stream'
    with M.NeighborhoodFile.create(
        content_type=content_type,
        filename=file_name,
        neighborhood_id=n_adobe._id) as fp:
        while True:
            s = f.read()
            if not s: break
            fp.write(s)
    log.info('Registering "regular users" (non-root)')
    u_adobe = M.User.register(dict(username='adobe_admin',
                                   display_name='Adobe Admin'))
    u0 = M.User.register(dict(username='test_admin',
                              display_name='Test Admin'))
    u1 = M.User.register(dict(username='test_user',
                              display_name='Test User'))
    u2 = M.User.register(dict(username='test_user2',
                              display_name='Test User 2'))
    n_adobe.acl['admin'].append(u_adobe._id)
    u_adobe.set_password('foo')
    u0.set_password('foo')
    u1.set_password('foo')
    u0.claim_address('Beta@wiki.test.projects.sourceforge.net')

    log.info('Creating basic project categories')
    cat1 = M.ProjectCategory(name='clustering', label='Clustering')

    cat2 = M.ProjectCategory(name='communications', label='Communications')
    cat2_1 = M.ProjectCategory(name='synchronization', label='Synchronization', parent_id=cat2._id)
    cat2_2 = M.ProjectCategory(name='streaming', label='Streaming', parent_id=cat2._id)
    cat2_3 = M.ProjectCategory(name='fax', label='Fax', parent_id=cat2._id)
    cat2_4 = M.ProjectCategory(name='bbs', label='BBS', parent_id=cat2._id)

    cat3 = M.ProjectCategory(name='database', label='Database')
    cat3_1 = M.ProjectCategory(name='front_ends', label='Front-Ends', parent_id=cat3._id)
    cat3_2 = M.ProjectCategory(name='engines_servers', label='Engines/Servers', parent_id=cat3._id)

    log.info('Registering initial projects')
    p_adobe1 = n_adobe.register_project('adobe_1', u_adobe)
    p_adobe2 = n_adobe.register_project('adobe_2', u_adobe)
    p0 = n_projects.register_project('test', u0)
    c.project = p0
    c.user = u0
    p1 = p0.new_subproject('sub1')
    ThreadLocalORMSession.flush_all()
    if asbool(conf.get('load_test_data')):
        log.info('Loading test data')
        u_proj = M.Project.query.get(shortname='u/test_admin')
        u_proj.new_subproject('sub1')
        app = p0.install_app('hello_forge', 'hello')
        app = p0.install_app('SVN', 'src')
        app = p0.install_app('Git', 'src_git')
        app.config.options['type'] = 'git'
        app = p0.install_app('Hg', 'src_hg')
        app.config.options['type'] = 'hg'
        p0.install_app('Wiki', 'wiki')
        p0.install_app('Tickets', 'bugs')
        p0.install_app('Tickets', 'doc_bugs')
        p0.install_app('Discussion', 'discussion')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        if asbool(conf.get('cache_test_data')):
            cache_test_data()
    else: # pragma no cover
        log.info('Loading some large data')
        p0.install_app('Wiki', 'wiki')
        p0.install_app('Tickets', 'bugs')
        p0.install_app('Discussion', 'discussion')
        # app = p0.install_app('SVN', 'src')
        # app = p0.install_app('Git', 'src_git')
        ThreadLocalORMSession.flush_all()
        for msg in c.queued_messages:
            g._publish(**msg)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()


def wipe_database():
    conn = M.main_doc_session.bind.conn
    cmd = MigrateCommand('flyway')
    if isinstance(conn, mim.Connection):
        for db in conn.database_names():
            db=conn[db]
            for coll in db.collection_names():
                coll = db[coll]
                coll._data = {}
            cmd.run(['-u', 'mim:///'+db.name])
    else:
        for database in conn.database_names():
            log.info('Wiping database %s', database)
            db = conn[database]
            for coll in db.collection_names():
                if coll.startswith('system.'): continue
                log.info('Dropping collection %s:%s', database, coll)
                try:
                    db.drop_collection(coll)
                except:
                    pass
        # Run flyway
        cmd.run(['-u', 'ming://%s:%s/' % (conn.host, conn.port)])

def create_user(display_name):
    user = M.User.register(dict(username=display_name.lower(),
                                display_name=display_name),
                           make_project=False)
    user.set_password('foo')
    return user


class DBSession(Session):
    '''Simple session that takes a pymongo connection and a database name'''

    def __init__(self, db):
        self._db = db

    @property
    def db(self):
        return self._db

    def _impl(self, cls):
        return self.db[cls.__mongometa__.name]

def pm(etype, value, tb): # pragma no cover
    import pdb, traceback
    try:
        from IPython.ipapi import make_session; make_session()
        from IPython.Debugger import Pdb
        sys.stderr.write('Entering post-mortem IPDB shell\n')
        p = Pdb(color_scheme='Linux')
        p.reset()
        p.setup(None, tb)
        p.print_stack_trace()
        sys.stderr.write('%s: %s\n' % ( etype, value))
        p.cmdloop()
        p.forget()
        # p.interaction(None, tb)
    except ImportError:
        sys.stderr.write('Entering post-mortem PDB shell\n')
        traceback.print_exception(etype, value, tb)
        pdb.post_mortem(tb)

sys.excepthook = pm
