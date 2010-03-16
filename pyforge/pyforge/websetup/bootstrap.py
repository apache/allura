# -*- coding: utf-8 -*-
"""Setup the pyforge application"""
import os
import sys
import logging
import shutil
from datetime import datetime
from mimetypes import guess_type
from tg import config
from pylons import c, g
from paste.deploy.converters import asbool

from ming.orm.base import session
from ming.orm.ormsession import ThreadLocalORMSession

import pyforge
from pyforge import model as M

log = logging.getLogger(__name__)

def cache_test_data():
    log.info('Saving data to cache in .test-data')
    if os.path.exists('.test-data'):
        shutil.rmtree('.test-data')
    os.system('mongodump -o .test-data > mongodump.log')

def restore_test_data():
    if os.path.exists('.test-data'):
        log.info('Restoring data from cache in .test-data')
        rc = os.system('mongorestore --dir .test-data > mongorestore.log')
        return rc == 0
    else:
        return False

def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""
    # Clean up all old stuff
    ThreadLocalORMSession.close_all()
    c.queued_messages = []
    database=conf.get('db_prefix', '') + 'project:test'
    conn = M.main_doc_session.bind.conn
    for database in conn.database_names():
        db = conn[database]
        for coll in db.collection_names():
            if coll.startswith('system.'): continue
            log.info('Dropping collection %s:%s', database, coll)
            try:
                db.drop_collection(coll)
            except:
                pass
    g._push_object(pyforge.lib.app_globals.Globals())
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
    root = M.User.register(dict(username='root', display_name='Root'),
                           make_project=False)
    root.set_password('foo')
    n_projects = M.Neighborhood(name='Projects',
                                url_prefix='/projects/',
                                acl=dict(read=[None], create=[],
                                         moderate=[root._id], admin=[root._id]))
    n_users = M.Neighborhood(name='Users',
                             url_prefix='/users/',
                             shortname_prefix='users/',
                             acl=dict(read=[None], create=[],
                                      moderate=[root._id], admin=[root._id]))
    n_adobe = M.Neighborhood(name='Adobe',
                             url_prefix='/adobe/',
                               css="""
#nav_menu{
 background-color: #000;
 background-image: url(/images/adobe_header.png);
 color: #fff;
 border-width: 0;
}
#nav_menu a.neighborhood_name:link, 
#nav_menu a.neighborhood_name:visited, 
#nav_menu a.neighborhood_name:hover, 
#nav_menu a.neighborhood_name:active, 
#nav_menu a.project_name:link, 
#nav_menu a.project_name:visited, 
#nav_menu a.project_name:hover, 
#nav_menu a.project_name:active{
 color: #fff;
}
#nav_menu ul.nav_links a:link, 
#nav_menu ul.nav_links a:visited, 
#nav_menu ul.nav_links a:hover, 
#nav_menu ul.nav_links a:active{
 color: #fff;
}
#nav_menu ul.nav_links a.active:link, 
#nav_menu ul.nav_links a.active:visited, 
#nav_menu ul.nav_links a.active:hover, 
#nav_menu ul.nav_links a.active:active{
 color: #000;
 background-color: #fff;
 -moz-border-radius: 3px 3px 0 0;
 -webkit-border-radius: 3px 3px 0 0;
}

#nav_menu .home_icon{
   background-image: url(/images/white_home.png);
   background-repeat: no-repeat;
   background-position:center 7px;
}

#nav_menu .home_icon.active{
   background-image: url(/images/black_home.png);
}
#content_holder{
 border-color: #000;
 border-width: 0 5px 5px 5px;
 width: 940px;
}
#content{
 border-width: 0;
}
ul#sidebarmenu li a.active {
 background-color: #000;
 color: #fff;
}""",
                             acl=dict(read=[None], create=[],
                                      moderate=[root._id], admin=[root._id]))
    n_mozilla = M.Neighborhood(name='Mozilla',
                               url_prefix='/mozilla/',
                               acl=dict(read=[None], create=[],
                                        moderate=[root._id], admin=[root._id]))
    M.Theme(name='forge_default',
            label='Default Forge Theme',
            color1='#536BB2',
            color2='#aed0ea',
            color3='#EDF3FB')
    M.Theme(neighborhood_id = n_mozilla._id,
            color1='#ccc',
            color2='#666',
            color3='#333')
    ThreadLocalORMSession.flush_all()
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
    u_mozilla = M.User.register(dict(username='mozilla_admin',
                                     display_name='Mozilla Admin'))
    u_adobe = M.User.register(dict(username='adobe_admin',
                                   display_name='Adobe Admin'))
    u0 = M.User.register(dict(username='test_admin',
                              display_name='Test Admin'))
    u1 = M.User.register(dict(username='test_user',
                              display_name='Test User'))
    u2 = M.User.register(dict(username='test_user2',
                              display_name='Test User 2'))
    n_adobe.acl['admin'].append(u_adobe._id)
    n_mozilla.acl['admin'].append(u_mozilla._id)
    u_mozilla.set_password('foo')
    u_adobe.set_password('foo')
    u0.set_password('foo')
    u1.set_password('foo')
    u0.claim_address('Beta@wiki.test.projects.sourceforge.net')
    log.info('Registering initial projects')
    p_adobe1 = n_adobe.register_project('Adobe 1', u_adobe)
    p_adobe2 = n_adobe.register_project('Adobe 2', u_adobe)
    p_mozilla = n_mozilla.register_project('Mozilla 1', u_mozilla)
    p0 = n_projects.register_project('test', u0)
    c.project = p0
    c.user = u0
    p0.acl['read'].append(u1.project_role(p0)._id)
    p1 = p0.new_subproject('sub1')
    ThreadLocalORMSession.flush_all()
    if asbool(conf.get('load_test_data')):
        log.info('Loading test data')
        app = p0.install_app('hello_forge', 'hello')
        app = p0.install_app('Repository', 'src')
        app = p0.install_app('Repository', 'src_git')
        p0.install_app('Wiki', 'wiki')
        p0.install_app('Tickets', 'bugs')
        p0.install_app('Tickets', 'doc_bugs')
        p0.install_app('Forum', 'Forum')
        app.config.options['type'] = 'git'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        if asbool(conf.get('cache_test_data')):
            cache_test_data()
    else: # pragma no cover
        log.info('Loading some large data')
        p0.install_app('Wiki', 'wiki')
        p0.install_app('Tickets', 'bugs')
        p0.install_app('Forum', 'forum')
        # app = p0.install_app('Repository', 'src')
        # app = p0.install_app('Repository', 'src_git')
        dev = M.ProjectRole(name='developer')
        ThreadLocalORMSession.flush_all()
        for ur in M.ProjectRole.query.find():
            if ur.name and ur.name[:1] == '*': continue
            ur.roles.append(dev._id)
        ThreadLocalORMSession.flush_all()
        for msg in c.queued_messages:
            g._publish(**msg)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

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
