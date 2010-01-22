# -*- coding: utf-8 -*-
"""
Model tests for artifact
"""
import re
import os
from datetime import datetime
from time import sleep

from pylons import c, g
from nose.tools import assert_true
import markdown
import mock

import pymongo
from pymongo.errors import OperationFailure

from ming import schema as S
from ming.base import Object
from ming.orm.property import FieldProperty

from pyforge.model import Artifact, Message, AppConfig
from pyforge.lib.app_globals import Globals

PROJECT = mock.Mock()
PROJECT.name = 'Test Project'
PROJECT.shortname = 'tp'
PROJECT._id = 'testproject/'
PROJECT.database = 'nosetest:project'
PROJECT.url = lambda: '/testproject/'
APP_CONFIG = mock.Mock()
APP_CONFIG._id = None
APP_CONFIG.project_id = 'testproject/'
APP_CONFIG.plugin_name = 'plugin'
APP_CONFIG.options = Object(mount_point = 'foo')
APP = mock.Mock()
APP.config = APP_CONFIG
APP.config.script_name = lambda:'test_application'
APP.__version__ = '0.0'

class Checkmessage(Message):
    class __mongometa__:
        name='checkmessage'
    page_title=FieldProperty(str)
    project=PROJECT
    app_config=APP_CONFIG
    def url(self):
        return ''
    def index(self):
        return dict()
    def shorthand_id(self):
        return ''

def setUp():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    c.app = APP
    c.user._id = None
    c.project = PROJECT
    
def test_artifact():
    class Checkartifact(Artifact):
        class __mongometa__:
            name='checkartifact'
        title=FieldProperty(str)
        version=FieldProperty(int, if_missing=0)
        author_id=FieldProperty(S.ObjectId, if_missing=lambda:c.user._id)
        timestamp=FieldProperty(S.DateTime, if_missing=datetime.utcnow)
        text=FieldProperty(S.String, if_missing='')

    assert_true('PyForge has available model::Artifact class')

def test_message_author():
    m = Checkmessage(page_title='test_title')
    m.author()
    assert_true('PyForge message has author')

def test_message_reply():
    m = Checkmessage(page_title='test_title')
    m.reply()
    assert_true('PyForge message has reply')

def test_message_descendants():
    m = Checkmessage(page_title='test_title')
    m.descendants()
    assert_true('PyForge message has descendants')

def test_message_replies():
    m = Checkmessage(page_title='test_title')
    m.replies()
    assert_true('PyForge message has replies')

