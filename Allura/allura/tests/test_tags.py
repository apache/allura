from os import path, environ

import mock

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g
from ming.orm.ormsession import ThreadLocalORMSession

from allura.command import reactor
from allura import model as M
from allura.lib import helpers as h
from forgewiki import model as WM

def setUp(self):
    """Method called by nose before running each test"""
    test_config = environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini'

    # Loading the application:
    conf_dir = config.here
    wsgiapp = loadapp('config:%s#main' % test_config,
                      relative_to=conf_dir)
    # Setting it up:
    test_file = path.join(conf_dir, test_config)
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])
    ThreadLocalORMSession.flush_all()

def test_tag_untag():
    h.set_context('test', 'wiki')
    pg = WM.Page.query.find().first()
    # Give page 2 tags
    h.tag_artifact(pg, M.User.anonymous(), ['test', 'wiki'])
    ThreadLocalORMSession.flush_all(); ThreadLocalORMSession.close_all()
    pg = WM.Page.query.find().first()
    assert M.UserTags.query.find(dict(user_id=None)).count() == 1
    assert M.Tag.query.find().count() == 2
    assert WM.Page.artifacts_tagged_with('test').count() == 1
    assert WM.Page.artifacts_tagged_with('wiki').count() == 1
    assert len(pg.tags) == 2
    # Remove 1
    h.tag_artifact(pg, M.User.anonymous(), ['test'])
    ThreadLocalORMSession.flush_all(); ThreadLocalORMSession.close_all()
    pg = WM.Page.query.find().first()
    assert M.UserTags.query.find(dict(user_id=None)).count() == 1
    assert M.Tag.query.find().count() == 1
    assert len(pg.tags) == 1
    assert WM.Page.artifacts_tagged_with('test').count() == 1
    assert WM.Page.artifacts_tagged_with('wiki').count() == 0
    # Remove last one
    h.tag_artifact(pg, M.User.anonymous(), [])
    ThreadLocalORMSession.flush_all(); ThreadLocalORMSession.close_all()
    pg = WM.Page.query.find().first()
    assert M.UserTags.query.find(dict(user_id=None)).count() == 0
    assert M.Tag.query.find().count() == 0
    assert len(pg.tags) == 0
    assert WM.Page.artifacts_tagged_with('test').count() == 0
    assert WM.Page.artifacts_tagged_with('wiki').count() == 0
