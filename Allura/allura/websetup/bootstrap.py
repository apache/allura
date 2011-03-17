# -*- coding: utf-8 -*-
"""Setup the allura application"""
import os
import sys
import logging
import shutil
from collections import defaultdict
from datetime import datetime

import tg
from pylons import c, g
from paste.deploy.converters import asbool

from flyway.command import MigrateCommand
from flyway.model import MigrationInfo
from ming import Session, mim
from ming.orm import state, session
from ming.orm.ormsession import ThreadLocalORMSession

import allura
from allura.lib import plugin
from allura import model as M
from allura.websetup import schema
from allura.command import EnsureIndexCommand

log = logging.getLogger(__name__)

def set_flyway_info():
    versions = dict(
        allura=1,
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
    """Place any commands to setup allura here"""
    # Our bootstrap doesn't play nicely with SFX project and user APIs
    tg.config['auth.method'] = tg.config['registration.method'] = 'local'
    assert tg.config['auth.method'] == 'local'
    conf['auth.method'] = conf['registration.method'] = 'local'
    # Clean up all old stuff
    ThreadLocalORMSession.close_all()
    c.queued_messages = defaultdict(list)
    c.user = c.project = c.app = None
    database=conf.get('db_prefix', '') + 'project:test'
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
    assert tg.config['auth.method'] == 'local'
    project_reg = plugin.ProjectRegistrationProvider.get()
    p_projects = project_reg.register_neighborhood_project(n_projects, [root])
    p_users = project_reg.register_neighborhood_project(n_users, [root])
    p_adobe = project_reg.register_neighborhood_project(n_adobe, [root])
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

    # add the adobe icon
    file_name = 'adobe_icon.png'
    file_path = os.path.join(allura.__path__[0],'public','nf','images',file_name)
    M.NeighborhoodFile.from_path(file_path, neighborhood_id=n_adobe._id)
    log.info('Registering "regular users" (non-root)')
    u_adobe = M.User.register(dict(username='adobe-admin',
                                   display_name='Adobe Admin'))
    u0 = M.User.register(dict(username='test-admin',
                              display_name='Test Admin'))
    u1 = M.User.register(dict(username='test-user',
                              display_name='Test User'))
    u2 = M.User.register(dict(username='test-user2',
                              display_name='Test User 2'))
    u_admin1 = M.User.register(dict(username='admin1',
                                    display_name='Admin 1'))
    n_adobe.acl['admin'].append(u_adobe._id)
    # Admin1 is almost root, with admin access for Users and Projects neighborhoods
    n_projects.acl['admin'].append(u_admin1._id)
    n_users.acl['admin'].append(u_admin1._id)
    # Ming doesn't detect substructural changes in newly created objects (vs loaded from DB)
    state(n_adobe).status = 'dirty'
    state(n_projects).status = 'dirty'
    state(n_users).status = 'dirty'
    # TODO: Hope that Ming can be improved to at least avoid stuff below
    session(n_adobe).flush(n_adobe)
    session(n_projects).flush(n_projects)
    session(n_users).flush(n_users)

    u_adobe.set_password('foo')
    u0.set_password('foo')
    u1.set_password('foo')
    u2.set_password('foo')
    u_admin1.set_password('foo')
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
    p_adobe1 = n_adobe.register_project('adobe-1', u_adobe)
    p_adobe2 = n_adobe.register_project('adobe-2', u_adobe)
    p_allura = n_projects.register_project('allura', u_admin1)
    p0 = n_projects.register_project('test', u0)
    p0._extra_tool_status = [ 'alpha', 'beta' ]

    c.project = p0
    c.user = u0
    p0.add_user(u_admin1, ['Admin'])
    p1 = p0.new_subproject('sub1')
    ThreadLocalORMSession.flush_all()
    if asbool(conf.get('load_test_data')):
        log.info('Loading test data')
        u_proj = M.Project.query.get(shortname='u/test-admin')
        u_proj.new_subproject('sub1')
        app = p0.install_app('SVN', 'src', 'SVN')
        app = p0.install_app('Git', 'src-git', 'Git')
        app.config.options['type'] = 'git'
        app = p0.install_app('Hg', 'src-hg', 'Mercurial')
        app.config.options['type'] = 'hg'
        p0.install_app('Wiki', 'wiki')
        p0.install_app('Tickets', 'bugs')
        p0.install_app('Tickets', 'doc-bugs')
        p0.install_app('Discussion', 'discussion')
        p0.install_app('Link', 'link')
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
        # app = p0.install_app('Git', 'src-git')
        ThreadLocalORMSession.flush_all()
        g.send_all_messages()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

def wipe_database():
    conn = M.main_doc_session.bind.conn
    flyway = MigrateCommand('flyway')
    index = EnsureIndexCommand('ensure_index')
    if isinstance(conn, mim.Connection):
        clear_all_database_tables()
        for db in conn.database_names():
            db = conn[db]
            flyway.run(['--force', '-u', 'mim:///'+db.name])
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
        flyway.run(['--force', '-u', 'mongodb://%s:%s/' % (conn.host, conn.port)])
    index.run([])


def clear_all_database_tables():
    conn = M.main_doc_session.bind.conn
    for db in conn.database_names():
        db = conn[db]
        for coll in db.collection_names():
            db.drop_collection(coll)


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
