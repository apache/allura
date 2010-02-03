from nose.tools import assert_true, assert_false
from forgetracker.tests import TestController
from pyforge import model


class TestFunctionalController(TestController):

    def test_new_ticket(self):
        response = self.app.get('/bugs/new/')
        form = response.form
        summary = 'test new ticket'
        form['summary'] = summary
        response = form.submit().follow()
        assert_true(summary in response)
        response = self.app.get('/bugs/')
        assert_true(summary in response)

    def test_two_trackers(self):
        response = self.app.get('/doc_bugs/new/')
        form = response.form
        summary = 'test two trackers'
        form['summary'] = summary
        response = form.submit().follow()
        assert_true(summary in response)
        response = self.app.get('/bugs/')
        assert_false(summary in response)

    def test_new_comment(self):
        response = self.app.get('/bugs/new/')
        form = response.form
        form['summary'] = 'test new comment'
        form.submit()
        comment = 'comment testing new comment'
        self.app.post('/bugs/1/comments/reply', { 'text': comment })
        response = self.app.get('/bugs/1/')
        assert_true(comment in response)
