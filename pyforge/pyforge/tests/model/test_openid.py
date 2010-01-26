# -*- coding: utf-8 -*-
"""
Model tests for openid_model
"""
import time

import mock
from pylons import c, g, request
from webob import Request
from openid.association import Association

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.lib.app_globals import Globals
from pyforge import model as M
from pyforge.lib import helpers as h

def setUp():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    M.EmailAddress.query.remove({})
    M.OpenIdNonce.query.remove({})
    M.OpenIdAssociation.query.remove({})
    conn = M.main_doc_session.bind.conn
    g.set_project('projects/test')
    g.set_app('hello')
    c.user = M.User.query.get(username='test_admin')
    c.user.email_addresses = c.user.open_ids = []
    c.user.projects = c.user.projects[:2]
    c.user.project_role().roles = []

def test_oid_model():
    oid = M.OpenIdAssociation(_id='http://example.com')
    assoc = mock.Mock()
    assoc.handle = 'foo'
    assoc.serialize = lambda:'bar'
    assoc.getExpiresIn = lambda:0
    with h.push_config(Association,
                       deserialize=staticmethod(lambda v:assoc)):
        oid.set_assoc(assoc)
        assert assoc == oid.get_assoc('foo')
        oid.set_assoc(assoc)
        oid.remove_assoc('foo')
        assert oid.get_assoc('foo') is None
        oid.set_assoc(assoc)
        assert oid.get_assoc('foo') is not None
        oid.cleanup_assocs()
        assert oid.get_assoc('foo') is None

def test_oid_store():
    assoc = mock.Mock()
    assoc.handle = 'foo'
    assoc.serialize = lambda:'bar'
    assoc.getExpiresIn = lambda:0
    store = M.OpenIdStore()
    with h.push_config(Association,
                       deserialize=staticmethod(lambda v:assoc)):
        store.storeAssociation('http://example.com', assoc)
        assert assoc == store.getAssociation('http://example.com', 'foo')
        assert assoc == store.getAssociation('http://example.com')
        store.removeAssociation('http://example.com', 'foo')
        t0 = time.time()
        assert store.useNonce('http://www.example.com', t0, 'abcd')
        ThreadLocalORMSession.flush_all()
        assert not store.useNonce('http://www.example.com', t0, 'abcd')
        assert not store.useNonce('http://www.example.com', t0-1e9, 'abcd')
        assert store.getAssociation('http://example.com') is None
        store.cleanupNonces()
