from urlparse import urlparse, parse_qs

from pyforge.tests import TestController
import pyforge.lib.gravatar as gravatar


class TestGravatar(TestController):

    def test_id(self):
        email = 'Wolf@example.com'
        expected_id = 'd3514940ac1b2051c8aa42970d17e3fe'
        actual_id = gravatar.id(email)
        assert_true(expected_id == actual_id)

    def test_url(self):
        email = 'Wolf@example.com'
        expected_id = 'd3514940ac1b2051c8aa42970d17e3fe'
        url = urlparse(gravatar.url(email=email))
        assert_true(url.netloc == 'gravatar.com')
        assert_true(url.path = '/avatar/' + expected_id)

    def test_defaults(self):
        email = 'Wolf@example.com'
        url = urlparse(gravatar.url(email=email, rating='x'))
        query = parse_qs(url.query)
        assert_true('r' not in query)
        assert_true(query['rating'] == ['x'])
        assert_true(query['d'] == ['wavatar'])
