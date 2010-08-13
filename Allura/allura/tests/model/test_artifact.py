# -*- coding: utf-8 -*-
"""
Model tests for artifact
"""
import re
from datetime import datetime

from pylons import c, g
from nose.tools import assert_raises
import mock

from ming import schema as S
from ming.base import Object
from ming.orm.property import FieldProperty
from ming.orm.ormsession import ThreadLocalORMSession

import allura.model.artifact
from allura import model as M
from allura.lib import helpers as h
from allura.lib.custom_middleware import MagicalC, environ as ENV
from allura.lib.app_globals import Globals
from helloforge import model as HM

class Checkmessage(M.Message):
    class __mongometa__:
        name='checkmessage'
    def url(self):
        return ''
    def __init__(self, **kw):
        super(Checkmessage, self).__init__(**kw)
        if self.slug is not None and self.full_slug is None:
            self.full_slug = datetime.utcnow().strftime('%Y%m%d%H%M%S') + ':' + self.slug
Checkmessage.compile_all()

def setUp():
    g._push_object(Globals())
    c._push_object(MagicalC(mock.Mock(), ENV))
    ThreadLocalORMSession.close_all()
    g.set_project('test')
    g.set_app('hello')
    Checkmessage.query.remove({})
    HM.Page.query.remove({})
    HM.PageHistory.query.remove({})
    M.ArtifactLink.query.remove({})
    c.user = M.User.query.get(username='test-admin')
    Checkmessage.project = c.project
    Checkmessage.app_config = c.app.config

def tearDown():
    ThreadLocalORMSession.close_all()

def test_artifact():
    pg = HM.Page(title='TestPage1')
    assert pg.project == c.project
    assert pg.project_id == c.project._id
    assert pg.app.config == c.app.config
    assert pg.app_config == c.app.config
    u = M.User.query.get(username='test-user')
    pg.give_access('delete', user=u)
    ThreadLocalORMSession.flush_all()
    assert u.project_role()._id in pg.acl['delete']
    pg.revoke_access('delete', user=u)
    assert u.project_role()._id not in pg.acl['delete']
    idx = pg.index()
    assert 'title_s' in idx
    assert 'url_s' in idx
    assert 'project_id_s' in idx
    assert 'mount_point_s' in idx
    assert 'type_s' in idx
    assert 'id' in idx
    assert idx['id'] == pg.index_id()
    assert 'text' in idx
    assert 'TestPage' in pg.shorthand_id()

def test_artifactlink():
    pg = HM.Page(title='TestPage2')
    q = M.ArtifactLink.query.find(dict(
            project_id=c.project._id,
            mount_point='hello',
            link=pg.shorthand_id()))
    assert q.count() == 0
    ThreadLocalORMSession.flush_all()
    assert q.count() == 1
    assert M.ArtifactLink.lookup('[TestPage2]')
    assert M.ArtifactLink.lookup('[hello:TestPage2]')
    assert M.ArtifactLink.lookup('[hello_forge:TestPage2]')
    assert M.ArtifactLink.lookup('[/test:hello:TestPage2]')
    assert M.ArtifactLink.lookup('[../test:hello:TestPage2]')
    assert not M.ArtifactLink.lookup('[TestPage2_no_such_page]')
    pg.delete()
    ThreadLocalORMSession.flush_all()
    assert q.count() == 0

def test_gen_messageid():
    assert re.match(r'[0-9a-zA-Z]*.hello@test.p.sourceforge.net', h.gen_message_id())

def test_versioning():
    pg = HM.Page(title='TestPage3')
    pg.commit()
    ThreadLocalORMSession.flush_all()
    pg.text = 'Here is some text'
    pg.commit()
    ThreadLocalORMSession.flush_all()
    ss = pg.get_version(1)
    assert ss.index()['is_history_b']
    assert ss.shorthand_id() == pg.shorthand_id() + '#1'
    assert ss.title == pg.title
    assert ss.text != pg.text
    ss = pg.get_version(-1)
    assert ss.index()['is_history_b']
    assert ss.shorthand_id() == pg.shorthand_id() + '#2'
    assert ss.title == pg.title
    assert ss.text == pg.text
    assert_raises(IndexError, pg.get_version, 42)
    pg.revert(1)
    pg.commit()
    ThreadLocalORMSession.flush_all()
    assert ss.text != pg.text
    assert pg.history().count() == 3

def test_messages():
    m = Checkmessage()
    assert m.author() == c.user
    rm1 = m.reply()
    assert rm1.slug.startswith(m.slug)
    rm2 = rm1.reply()
    rm3 = m.reply()
    ThreadLocalORMSession.flush_all()
    assert rm1 in list(m.descendants())
    assert rm2 in list(m.descendants())
    assert rm1 in list(m.replies())
    assert rm2 not in list(m.replies())
    idx = m.index()
    assert 'author_user_name_t' in idx
    assert 'author_display_name_t' in idx
    assert 'timestamp_dt' in idx
    assert m.shorthand_id() == m.slug
