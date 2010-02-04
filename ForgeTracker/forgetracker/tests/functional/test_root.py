from nose.tools import assert_true, assert_false
from forgetracker.tests import TestController
from pyforge import model


class TestFunctionalController(TestController):

    def new_ticket(self, summary, mp='/bugs/'):
        response = self.app.get(mp + 'new/')
        form = response.form
        form['summary'] = summary
        return form.submit().follow()

    def test_new_ticket(self):
        summary = 'test new ticket'
        response = self.new_ticket(summary)
        assert_true(summary in response)

    def test_two_trackers(self):
        summary = 'test two trackers'
        response = self.new_ticket(summary, '/doc_bugs/')
        assert_true(summary in response)
        response = self.app.get('/bugs/')
        assert_false(summary in response)

    def test_new_comment(self):
        self.new_ticket('test new comment')
        comment = 'comment testing new comment'
        self.app.post('/bugs/1/comments/reply', { 'text': comment })
        response = self.app.get('/bugs/1/')
        assert_true(comment in response)

    def test_render_ticket(self):
        summary = 'test render ticket'
        response = self.new_ticket(summary)
        assert_true(summary in response)
        assert_true('Comments' in response)
        assert_true('Make a comment' in response)

    def test_render_index(self):
        summary = 'test render index'
        self.new_ticket(summary)
        response = self.app.get('/bugs/')
        assert_true(summary in response)
