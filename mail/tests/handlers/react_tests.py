from nose.tools import *
from lamson.testing import *
import os
from lamson import server

relay = relay(port=8823)
client = RouterConversation("queuetester@localhost", "requests_tests")
confirm_format = "testing-confirm-[0-9]+@"
noreply_format = "testing-noreply@"

host = "localhost"

def test_react_for_existing_project():
    """
    Then make sure that project react messages for existing project queued properly.
    """
    dest_addr = "wiki.index@test.%s" % host
    client.begin()
    client.say(dest_addr, "Test project react messages for existing project queued properly")

def test_react_for_bad_project():
    """
    Then make sure that project react messages for non-existing project dropped properly.
    """
    dest_addr = "wiki.index@badproject.%s" % host
    client.begin()
    client.say(dest_addr, "Test project react messages for non-existing project dropped properly")

def test_react_for_user_project():
    """
    Then make sure that project react messages for existing user queued properly.
    """
    dest_addr = "wiki.index@test_user2.%s" % host
    client.begin()
    client.say(dest_addr, "Test project react messages for existing user queued properly")
