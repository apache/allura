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

from helloforge import model as HM

def setUp():
    from pyforge.tests import TestController
    TestController().setUp()
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    h.set_context('test', 'hello')
    c.user = M.User.query.get(username='test_admin')
    c.user.email_addresses = c.user.open_ids = []
    c.user.projects = c.user.projects[:2]
    c.user.project_role().roles = []

def test_index_artifact():
    a = HM.Page.query.find().first()
    search.add_artifacts([a])
    search.solarize(a)
    a.text = None
    search.remove_artifacts([a])
    search.search('Root')

def test_searchapp():
    app = search_main.SearchApp
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ 'test.ini' ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    add_artifacts = cmd.route_audit('search', app.add_artifacts)
    del_artifacts = cmd.route_audit('search', app.del_artifacts)
    msg = mock.Mock()
    msg.ack = lambda:None
    msg.delivery_info = dict(routing_key='search.add_artifacts')
    h.set_context('test', 'wiki')
    a = HM.Page.query.find().first()
    a.text = '\n[Root]\n'
    msg.data = dict(project_id=a.project_id,
                    mount_point=a.app_config.options.mount_point,
                    artifacts=[a.dump_ref()])
    add_artifacts(msg.data, msg)
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    a = HM.Page.query.find().first()
    assert len(a.references) == 1
    assert len(a.backreferences) == 1
    del_artifacts(msg.data, msg)
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    a = HM.Page.query.find().first()
    assert len(a.references) == 1
    assert len(a.backreferences) == 0


