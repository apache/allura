from unittest import TestCase

from pylons import c, g, h, url, request, response, translator
from webob import Request, Response
import mock

from ew import LinkField

class TestWidgets(TestCase):
    def setUp(self):
        g._push_object(mock.Mock())
        c._push_object(mock.Mock())
        h._push_object(mock.Mock())
        c.widget = None
        url._push_object(mock.Mock())
        translator._push_object(mock.Mock())
        request._push_object(Request.blank('/'))
        response._push_object(Response())

    def test_link_field(self):
        print LinkField().display()

