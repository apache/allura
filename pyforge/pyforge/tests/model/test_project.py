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

from pyforge.model import Project

database='project:nosetest'

def test_project_remove():
    Project.m.remove({})
    assert_true('PyForge model project can remove')

def test_project_make():
    p = Project.make(dict(_id='nosetest/', database=database, is_root=True))
    p.m.save()

    assert_true('PyForge model project can make and save')

def test_project_install():
    p = Project.make(dict(_id='nosetest/sub1/', database=database, is_root=True))
    p.m.save()
    p.uninstall_app('hello_forge')
    p.install_app('hello_forge')

    assert_true('PyForge model project can install and uninstall')


