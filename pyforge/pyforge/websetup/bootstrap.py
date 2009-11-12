# -*- coding: utf-8 -*-
"""Setup the pyforge application"""

import logging
from tg import config
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
    from pylons import c
    c.project = p0
    M.AppConfig.m.remove({})
    a = M.AppConfig.make(dict(name='hello_forge', project_id='test/',
                              config=dict(message='This is the message')))
    a.m.save()
            
