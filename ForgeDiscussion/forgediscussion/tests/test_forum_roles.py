from pylons import c, g

from pyforge.tests import helpers
from pyforge import model as M

def setUp():
    helpers.setup_basic_test()
    helpers.setup_global_objects()
    g.set_app('discussion')

def test_role_assignments():
    role_developer = M.ProjectRole.query.get(name='Developer')._id
    role_auth = M.ProjectRole.query.get(name='*authenticated')._id
    assert c.app.config.acl['configure'] == c.project.acl['plugin']
    assert c.app.config.acl['unmoderated_post'] == [role_developer]
    assert c.app.config.acl['post'] == [role_auth]
    assert c.app.config.acl['moderate'] == [role_developer]
    assert c.app.config.acl['admin'] == c.project.acl['plugin']
    
