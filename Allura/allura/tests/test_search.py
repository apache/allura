import os
from datetime import datetime, timedelta

import mock
from pylons import c, g, request
from webob import Request

from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.lib import search
from allura.lib import helpers as h
from allura.command import reactor
from allura.ext.search import search_main
from allura.lib.app_globals import Globals

from forgewiki import model as WM
from alluratest import controller


def setUp():
    controller.setup_basic_test()
    controller.setup_global_objects()

def test_index_artifact():
    app = M.Project.query.get(shortname='test').app_instance('wiki')
    a = WM.Page.query.get(app_config_id=app.config._id)
    search.add_artifacts([a])
    search.solarize(a)
    a.text = None
    search.remove_artifacts([a])
    g.solr.add([search.solarize(a)])
    r = search.search('WikiPage')
    assert r.hits == 1
    r = search.search_artifact(WM.Page, 'title:"WikiPage Home"')
    assert r.hits == 1
    r = search.search_artifact(WM.Page, 'title:"Home"')
    assert r.hits == 0

def test_searchapp():
    h.set_context('test', 'wiki')
    a = WM.Page.query.find().first()
    a.text = '\n[Home]\n'
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    g.mock_amq.setup_handlers()
    g.publish('react', 'artifacts_altered', dict(project_id=a.project_id,
                    mount_point=a.app_config.options.mount_point,
                    artifacts=[a.dump_ref()]))
    g.mock_amq.handle_all()
    a = WM.Page.query.find().first()
    assert len(a.references) == 1
    assert len(a.backreferences) == 1
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    g.mock_amq.handle_all()
    g.publish('react', 'artifacts_removed', dict(project_id=a.project_id,
                    mount_point=a.app_config.options.mount_point,
                    artifacts=[a.dump_ref()]))
    g.mock_amq.handle_all()
    a = WM.Page.query.find().first()
    assert len(a.references) == 1
    assert len(a.backreferences) == 0

def test_check_commit():
    # TODO: just coverage so far
    M.SearchConfig.query.remove()
    M.SearchConfig(last_commit = datetime.utcnow() - timedelta(days=1),
                   pending_commit = 1)
    g.publish('audit', 'search.check_commit', {})
    g.mock_amq.handle_all()
