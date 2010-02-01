from nose.tools import assert_true, assert_false
from forgetracker.tests import TestController
from pyforge import model


class TestFunctionalController(TestController):

    def test_new_ticket(self):
        response = self.app.get('/bugs/new/')
        form = response.form
        summary = 'first sample ticket'
        form['summary'] = summary
        response = form.submit().follow()
        assert_true(summary in response)
        response = self.app.get('/bugs/')
        assert_true(summary in response)

    def test_two_trackers(self):
        response = self.app.get('/doc_bugs/new/')
        form = response.form
        summary = 'first sample doc_bug'
        form['summary'] = summary
        response = form.submit().follow()
        assert_true(summary in response)
        response = self.app.get('/bugs/')
        assert_false(summary in response)
