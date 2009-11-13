# -*- coding: utf-8 -*-
"""Setup the pyforge application"""

import logging
from tg import config
from pylons import c
from pyforge import model as M

log = logging.getLogger(__name__)

def bootstrap(command, conf, vars):
    """Place any commands to setup pyforge here"""
    dburi='mongo://localhost:27017/project:test'
    database='project:test'
    M.Project.m.remove({})
    p0 = M.Project.make(dict(_id='test/', database=database, is_root=True))
    p1 = M.Project.make(dict(_id='test/sub1/', database=database, is_root=False))
    p0.m.save()
    p1.m.save()
    c.project = p0
    c.user = M.User.make(dict(_id=None, login='test_user',
                              display_name='Test User'))
    c.user.m.save()
    M.AppConfig.m.remove({})
    p0.uninstall_app('hello_forge')
    p0.install_app('hello_forge')
            
