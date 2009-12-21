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
from ming.orm.base import session

from pyforge.model import Project, User

database='project:nosetest'

def test_project_remove():
    Project.query.remove({})
    assert_true('PyForge model project can remove')

def test_project_make():
    p = Project(_id='nosetest/', database=database, is_root=True)
    session(p).flush()

    assert_true('PyForge model project can make and save')

def test_project_install():
    u = User(username='nosetest_user', display_name='Nose Test user')
    session(u).flush()
    p = u.register_project('nosetest_sub1')
    assert_true('PyForge model project can install and uninstall')


