# -*- coding: utf-8 -*-
"""Setup the pyforge application"""
import sys
import logging
from tg import config
from pylons import c, g
import pyforge
from pyforge import model as M

log = logging.getLogger(__name__)

def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""
    database=conf.get('db_prefix', '') + 'project:test'
    conn = M.User.m.session.bind.conn
    for database in conn.database_names():
        if (database.startswith('project:')
            or database.startswith('user:')
            or database.startswith('projects:')
            or database.startswith('users:')):
            log.info('Dropping database %s', database)
            conn.drop_database(database)
    M.User.m.remove({})
    M.Project.m.remove({})
    g._push_object(pyforge.lib.app_globals.Globals())
    try:
        g.solr.delete(q='*:*')
    except:
        log.exception('Error clearing solr index')
    log.info('Registering initial users')
    u0 = M.User.register(dict(username='test_admin', display_name='Test Admin'))
    u1 = M.User.register(dict(username='test_user', display_name='Test User'))
    u2 = M.User.register(dict(username='test_user2', display_name='Test User 2'))
    u0.set_password('foo')
    u1.set_password('foo')
    u0.m.save()
    u1.m.save()
    u2.m.save()
    log.info('Registering initial project')
    p0 = u0.register_project('test')
    p0.acl['read'].append(u1.project_role()._id)
    p1 = p0.new_subproject('sub1')
    p0.m.save()
    p1.m.save()
    c.user = u0
    p0.install_app('hello_forge', 'wiki')
    dev = M.ProjectRole.make(dict(name='developer'))
    dev.m.save()
    for ur in M.ProjectRole.m.find():
        if ur.name and ur.name[:1] == '*': continue
        ur.roles.append(dev._id)
        ur.m.save()

def pm(etype, value, tb):
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
