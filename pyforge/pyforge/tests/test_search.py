import mock
from pylons import c, g, request
from webob import Request

from ming.orm.ormsession import ThreadLocalORMSession

from pyforge import model as M
from pyforge.lib import search
from pyforge.lib.app_globals import Globals

from helloforge import model as HM

def setUp():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    request._push_object(Request.blank('/'))
    ThreadLocalORMSession.close_all()
    g.set_project('projects/test')
    g.set_app('hello')
    c.user = M.User.query.get(username='test_admin')
    c.user.email_addresses = c.user.open_ids = []
    c.user.projects = c.user.projects[:2]
    c.user.project_role().roles = []

def test_index_artifact():
    a = HM.Page.query.find().first()
    search.add_artifact(a)
    search._solarize(a)
    a.text = None
    search.ref_to_solr(search._obj_to_ref(a))
    search.remove_artifact(a)
    search.search('Root')
