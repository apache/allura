# -*- coding: utf-8 -*-
"""
Nosetest modules
"""
from nose.tools import *
import os
"""
Model tests for artifact
"""
from datetime import datetime
from time import sleep

from pylons import c
import re
import markdown

import pymongo
from pymongo.errors import OperationFailure

from ming import schema as S
from ming import Field

from pyforge.model import Artifact, Message

def test_artifact():
    class Checkartifact(Artifact):
        class __mongometa__:
            name='checkartifact'
        title=Field(str)
        version=Field(int, if_missing=0)
        author_id=Field(S.ObjectId, if_missing=lambda:c.user._id)
        timestamp=Field(S.DateTime, if_missing=datetime.utcnow)
        text=Field(S.String, if_missing='')

    assert_true('PyForge has available model::Artifact class')

def test_message():
    class Checkmessage(Message):
        class __mongometa__:
            name='checkmessage'
        page_title=Field(str)

    assert_true('PyForge has available model::Message class')

