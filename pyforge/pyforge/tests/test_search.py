import os

import mock
from pylons import c, g, request
from webob import Request

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge import model as M
from pyforge.lib import search
from pyforge.lib import helpers as h
from pyforge.command import reactor
from pyforge.ext.search import search_main
from pyforge.lib.app_globals import Globals

from forgewiki import model as WM

from . import helpers

def setUp():
    helpers.setup_basic_test()
    helpers.setup_global_objects()

def test_index_artifact():
    a = WM.Page.query.find().first()
    search.add_artifacts([a])
    search.solarize(a)
    a.text = None
    search.remove_artifacts([a])
    g.solr.add([search.solarize(a)])
    r = search.search('WikiPage')
    assert r.hits == 1
    r = search.search_artifact(WM.Page, 'title:"WikiPage WikiHome"')
    assert r.hits == 1
    r = search.search_artifact(WM.Page, 'title:"WikiHome"')
    assert r.hits == 0

def test_searchapp():
    h.set_context('test', 'wiki')
    a = WM.Page.query.find().first()
    a.text = '\n[WikiHome]\n'
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


