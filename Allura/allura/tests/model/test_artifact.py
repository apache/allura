# -*- coding: utf-8 -*-
"""
Model tests for artifact
"""
import re
from datetime import datetime

from pylons import c
from nose.tools import assert_raises
from nose import with_setup

from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import Mapper

import allura
from allura import model as M
from allura.lib import helpers as h
from allura.lib import security
from allura.websetup.schema import REGISTRY
from alluratest.controller import setup_basic_test, setup_unit_test
from forgewiki import model as WM

class Checkmessage(M.Message):
    class __mongometa__:
        name='checkmessage'
    def url(self):
        return ''
    def __init__(self, **kw):
        super(Checkmessage, self).__init__(**kw)
        if self.slug is not None and self.full_slug is None:
            self.full_slug = datetime.utcnow().strftime('%Y%m%d%H%M%S') + ':' + self.slug
Mapper.compile_all()

def setUp():
    setup_basic_test()
    setup_unit_test()
    h.set_context('test', 'wiki')
    Checkmessage.query.remove({})
    WM.Page.query.remove({})
    WM.PageHistory.query.remove({})
    M.Shortlink.query.remove({})
    c.user = M.User.query.get(username='test-admin')
    Checkmessage.project = c.project
    Checkmessage.app_config = c.app.config

def tearDown():
    ThreadLocalORMSession.close_all()

@with_setup(setUp, tearDown)
def test_artifact():
    pg = WM.Page(title='TestPage1')
    assert pg.project == c.project
    assert pg.project_id == c.project._id
    assert pg.app.config == c.app.config
    assert pg.app_config == c.app.config
    u = M.User.query.get(username='test-user')
    pr = u.project_role()
    ThreadLocalORMSession.flush_all()
    REGISTRY.register(allura.credentials, allura.lib.security.Credentials())
    assert not security.has_access(pg, 'delete')(user=u)
    pg.acl.append(M.ACE.allow(pr._id, 'delete'))
    ThreadLocalORMSession.flush_all()
    c.memoize_cache = {}
    assert security.has_access(pg, 'delete')(user=u)
    pg.acl.pop()
    ThreadLocalORMSession.flush_all()
    c.memoize_cache = {}
    assert not security.has_access(pg, 'delete')(user=u)
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
    assert pg.link_text() == pg.shorthand_id()

@with_setup(setUp, tearDown)
def test_artifactlink():
    pg = WM.Page(title='TestPage2')
    q = M.Shortlink.query.find(dict(
            project_id=c.project._id,
            app_config_id=c.app.config._id,
            link=pg.shorthand_id()))
    assert q.count() == 0
    ThreadLocalORMSession.flush_all()
    M.MonQTask.run_ready()
    ThreadLocalORMSession.flush_all()
    assert q.count() == 1
    assert M.Shortlink.lookup('[TestPage2]')
    assert M.Shortlink.lookup('[wiki:TestPage2]')
    assert M.Shortlink.lookup('[test:wiki:TestPage2]')
    assert not M.Shortlink.lookup('[Wiki:TestPage2]')
    assert not M.Shortlink.lookup('[TestPage2_no_such_page]')
    pg.delete()
    ThreadLocalORMSession.flush_all()
    M.MonQTask.run_ready()
    ThreadLocalORMSession.flush_all()
    assert q.count() == 0

@with_setup(setUp, tearDown)
def test_gen_messageid():
    assert re.match(r'[0-9a-zA-Z]*.wiki@test.p.sourceforge.net', h.gen_message_id())

@with_setup(setUp, tearDown)
def test_versioning():
    pg = WM.Page(title='TestPage3')
    pg.commit()
    ThreadLocalORMSession.flush_all()
    pg.text = 'Here is some text'
    pg.commit()
    ThreadLocalORMSession.flush_all()
    ss = pg.get_version(1)
    assert ss.author.logged_ip == '1.1.1.1'
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

@with_setup(setUp, tearDown)
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

@with_setup(setUp, tearDown)
def test_messages_unknown_lookup():
    from bson import ObjectId
    m = Checkmessage()
    m.author_id = ObjectId() # something new
    assert type(m.author()) == M.User, type(m.author())
    assert m.author() == M.User.anonymous()
