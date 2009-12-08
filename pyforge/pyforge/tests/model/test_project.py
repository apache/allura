# -*- coding: utf-8 -*-
"""
Nosetest modules
"""
from nose.tools import *
import os
"""
Model tests for project
"""
import logging

from pylons import c
import pkg_resources
from webob import exc

from ming import Document, Session, Field, datastore
from ming import schema as S

from pyforge.model import Project, User

database='project:nosetest'

def test_project_remove():
    Project.m.remove({})
    assert_true('PyForge model project can remove')

def test_project_make():
    p = Project.make(dict(_id='nosetest/', database=database, is_root=True))
    p.m.save()

    assert_true('PyForge model project can make and save')

def test_project_install():
    u = User.make(dict(username='nosetest_user', display_name='Nose Test user'))
    u.m.save()
    p = u.register_project('nosetest_sub1')
    assert_true('PyForge model project can install and uninstall')


