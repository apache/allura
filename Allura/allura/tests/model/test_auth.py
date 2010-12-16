# -*- coding: utf-8 -*-
"""
Model tests for auth
"""
import mock
from nose.tools import with_setup
from pylons import c, g, request
from webob import Request

from ming.orm.ormsession import ThreadLocalORMSession

import allura.model.auth
from allura.lib.app_globals import Globals
from allura import model as M
from allura.lib import plugin
from allura.tests import helpers

def setUp():
    helpers.setup_basic_test()
    ThreadLocalORMSession.close_all()
    helpers.setup_global_objects()

@with_setup(setUp)
def test_password_encoder():
    # Verify salt
    ep = plugin.LocalAuthenticationProvider(Request.blank('/'))._encode_password
    assert ep('test_pass') != ep('test_pass')
    assert ep('test_pass', '0000') == ep('test_pass', '0000')

@with_setup(setUp)
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

@with_setup(setUp)
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

@with_setup(setUp)
def test_user():
    assert c.user.url() .endswith('/u/test-admin/')
    assert c.user.script_name .endswith('/u/test-admin/')
    assert len(list(c.user.my_projects())) == 1
    assert M.User.anonymous().project_role().name == '*anonymous'
    u = M.User.register(dict(
            username='nosetest-user'))
    ThreadLocalORMSession.flush_all()
    assert u.private_project().shortname == 'u/nosetest-user'
    roles = list(u.role_iter())
    assert len(roles) == 3, roles
    u.set_password('foo')
    provider = plugin.LocalAuthenticationProvider(Request.blank('/'))
    assert provider._validate_password(u, 'foo')
    assert not provider._validate_password(u, 'foobar')
    u.set_password('foobar')
    assert provider._validate_password(u, 'foobar')
    assert not provider._validate_password(u, 'foo')

@with_setup(setUp)
def test_project_role():
    role = M.ProjectRole(project_id=c.project._id, name='test_role')
    c.user.project_role().roles.append(role._id)
    ThreadLocalORMSession.flush_all()
    for pr in c.user.role_iter():
        assert pr.display()
        pr.special
        assert pr.user in (c.user, None)
        list(pr.role_iter())

@with_setup(setUp)
def test_default_project_roles():
    roles = dict(
        (pr.name, pr)
        for pr in M.ProjectRole.query.find(dict(
                project_id=c.project._id)).all()
        if pr.name)
    # There're 2 users assigned to project, represented by
    # relational (vs named) ProjectRole's
    assert len(roles) == M.ProjectRole.query.find(dict(
        project_id=c.project._id)).count() - 2
    assert 'Admin' in roles.keys(), roles.keys()
    assert 'Developer' in roles.keys(), roles.keys()
    assert 'Member' in roles.keys(), roles.keys()
    assert roles['Developer']._id in roles['Admin'].roles
    assert roles['Member']._id in roles['Developer'].roles
