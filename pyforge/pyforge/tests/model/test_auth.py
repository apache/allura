# -*- coding: utf-8 -*-
"""
Nosetest modules
"""
from nose.tools import *
import os
"""
Model tests for auth
"""
from ming import Document, Session, Field
from ming import schema as S

from pyforge.model import User

database='project:nosetest'

def test_user():
    class Checkuser(User):
        class __mongometa__:
            name='checkuser'
            session = Session.by_name('main')

    _id=Field(S.ObjectId)
    login=Field(str)
    display_name=Field(str)
    groups=Field([str], if_empty=['*anonymous', '*authenticated' ])

    assert_true('PyForge has available model::User class')

def test_user_make():
    User.make
    user = User.make(dict(_id=None, login='nosetest_user', display_name='Nosetest User'))

    assert_true('PyForge model user can add a user')

