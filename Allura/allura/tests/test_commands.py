from os import path, environ

import mock
from nose.tools import assert_raises

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g

from allura.command import reactor, script
from allura import model as M
from allura.tests import helpers

test_config = '%s#main_with_amqp' % (
    environ.get('SANDBOX') and 'sandbox-test.ini' or 'test.ini')

def setUp(self):
    """Method called by nose before running each test"""
    helpers.setup_basic_test(app_name='main_with_amqp')

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
    def test_callback(callback, msg):
        msg.data = dict(project_id=malformed_id,
                mount_point='hello',
                user_id='badf00d')
        callback(msg.data, msg)
        msg.data = dict(project_id=bad_id,
                mount_point='hello',
                user_id='badf00d')
        callback(msg.data, msg)
        msg.data = dict(project_id=ok_id,
                mount_point='hello',
                user_id=M.User.anonymous()._id)
        callback(msg.data, msg)
        msg.data = dict(project_id=ok_id,
                mount_point='hello')
        callback(msg.data, msg)
        msg.data = dict(project_id=ok_id)
        callback(msg.data, msg)
        msg.data = dict()
        callback(msg.data, msg)
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ test_config ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    g.set_project('test')
    g.set_app('hello')
    a_callback = cmd.route_audit('hello_forge', c.app.__class__.auditor)
    ac_callback = cmd.route_audit('hello_forge', c.app.__class__.class_auditor)
    r_callback = cmd.route_react('hello_forge', c.app.__class__.reactor1)
    rc_callback = cmd.route_react('hello_forge', c.app.__class__.reactor3)
    msg = mock.Mock()
    msg.ack = lambda:None
    msg.delivery_info = dict(
        routing_key='hello_forge.test')
    test_callback(a_callback, msg)
    test_callback(ac_callback, msg)
    test_callback(r_callback, msg)
    test_callback(rc_callback, msg)

def test_send_message():
    cmd = reactor.SendMessageCommand('send_message')
    cmd.args = [ test_config, 'audit', 'nobody.listening', '{}' ]
    cmd.options = mock.Mock()
    cmd.options.context = '/p/test/hello/'
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
