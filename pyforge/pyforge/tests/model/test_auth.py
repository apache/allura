# -*- coding: utf-8 -*-
"""
Model tests for auth
"""
import mock
from nose.tools import assert_true
from pylons import c, g, request
from webob import Request

from ming.orm.ormsession import ThreadLocalORMSession

import pyforge.model.auth
from pyforge.lib.app_globals import Globals
from pyforge import model as M

def setUp():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    M.EmailAddress.query.remove({})
    M.OpenId.query.remove({})
    M.User.query.remove(dict(username='nosetest_user'))
    M.Project.query.remove(dict(_id='users/nosetest_user/'))
    M.Project.query.remove(dict(_id='test.projects:/'))
    conn = M.main_doc_session.bind.conn
    conn.drop_database('users:nosetest_user')
    conn.drop_database('domain:test:projects')
    g.set_project('projects/test')
    g.set_app('hello')
    c.user = M.User.query.get(username='test_admin')
    c.user.email_addresses = c.user.open_ids = []
    c.user.projects = c.user.projects[:2]
    c.user.project_role().roles = []
    M.ProjectRole.query.remove(dict(name='test_role'))

def test_password_encoder():
    # Verify salt
    assert M.auth.encode_password('test_pass') != M.auth.encode_password('test_pass')
    assert M.auth.encode_password('test_pass', '0000') == M.auth.encode_password('test_pass', '0000')

def test_email_address():
    addr = M.EmailAddress(_id='test_admin@sf.net', claimed_by_user_id=c.user._id)
    ThreadLocalORMSession.flush_all()
    assert addr.claimed_by_user() == c.user
    addr2 = M.EmailAddress.upsert('test@sf.net')
    addr3 = M.EmailAddress.upsert('test_admin@sf.net')
    assert addr3 is addr
    assert addr2 is not addr
    assert addr2
    addr4 = M.EmailAddress.upsert('test@SF.NET')
    assert addr4 is addr2
    addr.send_verification_link()
    assert addr is c.user.address_object('test_admin@sf.net')
    c.user.claim_address('test@SF.NET')
    assert 'test@sf.net' in c.user.email_addresses

def test_openid():
    oid = M.OpenId.upsert('http://google.com/accounts/1', 'My Google OID')
    oid.claimed_by_user_id = c.user._id
    ThreadLocalORMSession.flush_all()
    assert oid.claimed_by_user() is c.user
    assert M.OpenId.upsert('http://google.com/accounts/1', 'My Google OID') is oid
    ThreadLocalORMSession.flush_all()
    assert oid is c.user.openid_object(oid._id)
    c.user.claim_openid('http://google.com/accounts/2')
    oid2 = M.OpenId.upsert('http://google.com/accounts/2', 'My Google OID')
    assert oid2._id in c.user.open_ids
    ThreadLocalORMSession.flush_all()

def test_user():
    assert c.user.url() .endswith('/users/test_admin/')
    assert c.user.script_name .endswith('/users/test_admin/')
    assert len(list(c.user.my_projects())) == 2
    assert M.User.anonymous().project_role().name == '*anonymous'
    u = M.User.register(dict(
            username='nosetest_user'))
    ThreadLocalORMSession.flush_all()
    assert u.private_project()._id == 'users/nosetest_user/'
    assert len(list(u.role_iter())) == 3
    u.set_password('foo')
    assert u.validate_password('foo')
    assert not u.validate_password('foobar')
    u.set_password('foobar')
    assert u.validate_password('foobar')
    assert not u.validate_password('foo')
    p = u.register_project_domain('test.projects', 'TestProj')
    assert p._id == 'test.projects:/'
    assert p.name == 'TestProj'

def test_project_role():
    role = M.ProjectRole(name='test_role')
    c.user.project_role().roles.append(role._id)
    ThreadLocalORMSession.flush_all()
    for pr in c.user.role_iter():
        assert pr.display()
        pr.special
        assert pr.user in (c.user, M.User.anonymous())
        list(pr.role_iter())

