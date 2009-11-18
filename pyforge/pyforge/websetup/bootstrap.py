# -*- coding: utf-8 -*-
"""Setup the pyforge application"""
import sys
import logging
from tg import config
from pylons import c
from pyforge import model as M

log = logging.getLogger(__name__)

def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""
    dburi='mongo://localhost:27017/project:test'
    database='project:test'
    M.User.m.remove({})
    M.Project.m.remove({})
    u0 = M.User.make(dict(username='test_admin', display_name='Test Admin'))
    u1 = M.User.make(dict(username='test_user', display_name='Test User'))
    p0 = M.Project.make(dict(_id='test/', database=database, is_root=True))
    p1 = M.Project.make(dict(_id='test/sub1/', database=database, is_root=False))
    u0.set_password('foo')
    u1.set_password('foo')
    u0.m.save()
    u1.m.save()
    p0.allow_user(u0, 'create', 'read', 'delete', 'plugin', 'security')
    p0.allow_user(u1, 'read')
    p0.m.save()
    p1.m.save()
    c.project = p0
    c.user = u0
    M.AppConfig.m.remove({})
    p0.uninstall_app('hello_forge')
    p0.install_app('hello_forge')

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
        p.cmdloop()
        p.forget()
        # p.interaction(None, tb)
    except ImportError:
        sys.stderr.write('Entering post-mortem PDB shell\n')
        traceback.print_exception(etype, value, tb)
        pdb.post_mortem(tb)

sys.excepthook = pm
