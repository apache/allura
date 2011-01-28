import mock
from nose.tools import assert_raises
from datadiff.tools import assert_equal
import pylons

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import reactor, script
from allura import model as M


test_config = 'test.ini#main'

class EmptyClass(object): pass

def setUp(self):
    """Method called by nose before running each test"""
    #setup_basic_test(app_name='main_with_amqp')
    setup_basic_test()
    setup_global_objects()

def test_reactor_setup():
    cmd = reactor.ReactorSetupCommand('setup')
    cmd.args = [ test_config ]
    cmd.command()

def test_reactor():
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ test_config ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    cmd.multi_worker_main(configs)
    cmd.periodic_main()

def test_reactor_callbacks():
    ok_id = M.Project.query.get(shortname='test')._id
    bad_id = None
    malformed_id = 'foo'
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ test_config ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    pylons.g.set_project('test')
    pylons.g.set_app('wiki')
    
    react_method_vars = EmptyClass()
    def react_method(routing_key, doc):
        react_method_vars.routing_key = routing_key
        react_method_vars.doc = doc
        react_method_vars.c = EmptyClass()
        for attr in dir(pylons.c):
            if not attr.startswith('_'):
                setattr(react_method_vars.c, attr, getattr(pylons.c, attr))
    callback = cmd.route_react('Wiki', react_method)
    
    msg = mock.Mock()
    msg.ack = lambda:None
    msg.delivery_info = dict(
        routing_key='Wiki.test')
    
    # good message
    msg.data = dict(project_id=ok_id,
            mount_point='Wiki',
            user_id=M.User.query.get(username='test-user')._id)
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(project_id=ok_id, user_id=M.User.query.get(username='test-user')._id, mount_point='Wiki'))
    assert_equal(react_method_vars.c.user.username, 'test-user')
    assert_equal(react_method_vars.c.project.name, 'test')
    assert not hasattr(react_method_vars.c, 'app')
    
    # missing fields
    msg.data = dict(mount_point='Wiki')
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(mount_point='Wiki'))
    assert not hasattr(react_method_vars.c, 'user')
    assert not hasattr(react_method_vars.c, 'project')
    
    msg.data = dict(project_id=malformed_id,
            mount_point='Wiki',
            user_id=M.User.anonymous()._id)
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(project_id='foo', user_id=M.User.anonymous()._id, mount_point='Wiki'))
    assert_equal(react_method_vars.c.project, None)
    assert_equal(react_method_vars.c.user.username, '*anonymous')
    
    msg.data = dict(project_id=bad_id,
            mount_point='Wiki',
            user_id='badf00d')
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(project_id=bad_id, user_id='badf00d', mount_point='Wiki'))
    assert_equal(react_method_vars.c.project, None)
    assert not hasattr(react_method_vars.c, 'user')
    
    msg.data = dict(project_id=ok_id,
            mount_point='Wiki')
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(project_id=ok_id, mount_point='Wiki'))
    assert_equal(react_method_vars.c.project.name, 'test')
    assert not hasattr(react_method_vars.c, 'user')
    
    msg.data = dict(project_id=ok_id)
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict(project_id=ok_id))
    assert_equal(react_method_vars.c.project.name, 'test')
    assert not hasattr(react_method_vars.c, 'user')
    
    msg.data = dict()
    callback(msg.data, msg)
    assert_equal(react_method_vars.routing_key, 'Wiki.test')
    assert_equal(react_method_vars.doc, dict())
    assert not hasattr(react_method_vars.c, 'user')
    assert not hasattr(react_method_vars.c, 'project')
    assert not hasattr(react_method_vars.c, 'app')

def test_send_message():
    cmd = reactor.SendMessageCommand('send_message')
    cmd.args = [ test_config, 'audit', 'nobody.listening', '{}' ]
    cmd.options = mock.Mock()
    cmd.options.context = '/p/test/Wiki/'
    cmd.command()
    cmd.options.context = '/p/test/'
    cmd.command()
    cmd.options.context = None
    cmd.command()

def test_script():
    cmd = script.ScriptCommand('script')
    cmd.args = [ test_config, 'allura/tests/tscript.py' ]
    cmd.command()
    cmd.args = [ test_config, 'allura/tests/tscript_error.py' ]
    assert_raises(ValueError, cmd.command)
