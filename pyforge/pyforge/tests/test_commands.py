from os import path

import mock

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g

from pyforge.command import reactor
from pyforge import model as M

def setUp(self):
    """Method called by nose before running each test"""
    # Loading the application:
    conf_dir = config.here
    wsgiapp = loadapp('config:test.ini#main',
                      relative_to=conf_dir)
    # Setting it up:
    test_file = path.join(conf_dir, 'test.ini')
    cmd = SetupCommand('setup-app')
    cmd.run([test_file])

def test_reactor_setup():
    cmd = reactor.ReactorSetupCommand('setup')
    cmd.args = [ 'development.ini' ]
    cmd.command()

def test_reactor():
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ 'development.ini' ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    cmd.multi_worker_main(configs)
    cmd.periodic_main()

def test_reactor_callbacks():
    def test_callback(callback, msg):
        msg.data = dict(project_id='projects/test_badproject/',
                mount_point='hello',
                user_id='badf00d')
        callback(msg.data, msg)
        msg.data = dict(project_id='projects/test/',
                mount_point='hello',
                user_id=M.User.anonymous._id)
        callback(msg.data, msg)
        msg.data = dict(project_id='projects/test/',
                mount_point='hello')
        callback(msg.data, msg)
        msg.data = dict(project_id='projects/test/')
        callback(msg.data, msg)
        msg.data = dict()
        callback(msg.data, msg)
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ 'development.ini' ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    g.set_project('projects/test')
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
    cmd.args = [ 'development.ini', 'audit', 'nobody.listening', '{}' ]
    cmd.options = mock.Mock()
    cmd.options.context = 'projects/test/hello/'
    cmd.command()
    cmd.options.context = 'projects/test/'
    cmd.command()
    cmd.options.context = None
    cmd.command()

