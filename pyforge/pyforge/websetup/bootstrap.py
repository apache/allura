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
    if database in conn.database_names():
        conn.drop_database(database)
    M.User.m.remove({})
    M.Project.m.remove({})
    g._push_object(pyforge.lib.app_globals.Globals())
    try:
        g.solr.delete(q='*:*')
    except:
        log.exception('Error clearing solr index')
    u0 = M.User.make(dict(username='test_admin', display_name='Test Admin'))
    u1 = M.User.make(dict(username='test_user', display_name='Test User'))
    u0.set_password('foo')
    u1.set_password('foo')
    u0.m.save()
    u1.m.save()
    p0 = M.Project.make(dict(_id='test/', database=database, is_root=True))
    p0.install_app('admin', 'admin')
    p0.allow_user(u0, 'create', 'read', 'delete', 'plugin', 'security')
    p0.allow_user(u1, 'read')
    p1 = p0.new_subproject('sub1')
    p0.m.save()
    p1.m.save()
    c.user = u0
    p0.install_app('hello_forge', 'wiki')

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
