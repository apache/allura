from os import path

import mock

from tg import config
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from pylons import c, g
from ming.orm.ormsession import ThreadLocalORMSession

from pyforge.command import reactor
from pyforge import model as M
from pyforge.lib import helpers as h
from pyforge.ext.tag import TagApp
from forgewiki import model as WM

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

def test_tag_untag():
    # Don't save the TagEvent object (it would send messages via the reactor, not
    # what we want.)
    # Prepare reactor command
    cmd = reactor.ReactorCommand('reactor')
    cmd.args = [ 'test.ini' ]
    cmd.options = mock.Mock()
    cmd.options.dry_run = True
    cmd.options.proc = 1
    configs = cmd.command()
    callback = cmd.route_react('tag', TagApp.tag_event)
    msg = _tag_message()
    ThreadLocalORMSession.close_all()
    callback(msg.data, msg)
    assert M.UserTags.query.find(dict(user_id=None)).count() == 1
    assert M.Tag.query.find().count() == 2
    msg = _untag_message()
    ThreadLocalORMSession.close_all()
    callback(msg.data, msg)
    assert M.UserTags.query.find(dict(user_id=None)).count() == 0
    assert M.Tag.query.find().count() == 0

def _tag_message():
    # Create the 'tag' message
    c.user = M.User.anonymous()
    h.set_context('test', 'wiki')
    pg = WM.Page.query.find().first()
    evt = M.TagEvent.add(pg, [ 'cool', 'page' ])
    # Prepare mock message
    msg = mock.Mock()
    msg.ack = lambda:None
    msg.delivery_info = dict(
        routing_key='tag.event')
    msg.data = evt.as_message()
    return msg

def _untag_message():
    # Create the 'untag' message
    c.user = M.User.anonymous()
    h.set_context('test', 'wiki')
    pg = WM.Page.query.find().first()
    evt = M.TagEvent.remove(pg, [ 'cool', 'page' ])
    # Prepare mock message
    msg = mock.Mock()
    msg.ack = lambda:None
    msg.delivery_info = dict(
        routing_key='tag.event')
    msg.data = evt.as_message()
    return msg

