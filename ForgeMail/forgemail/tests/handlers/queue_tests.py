from lamson.testing import relay, RouterConversation
import os
from lamson import server

relay = relay(port=8823)
client = RouterConversation("queuetester@localhost", "requests_tests")
confirm_format = "testing-confirm-[0-9]+@"
noreply_format = "testing-noreply@"

host = "localhost"
project = "test"
list_name = "forge-list"
list_addr = "forge-list@%s" % host

def test_queue_mailing_list():
    """
    Then make sure that mailing list messages queued properly.
    """
    client.begin()
    client.say(list_addr, "Test mailing list queued properly")

