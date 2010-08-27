from allura.tests import TestController

class TestStatic(TestController):

    def test_static_controller(self):
        self.app.get('/nf/_static_/Wiki/js/browse.js')
        self.app.get('/nf/_static_/Wiki/js/no_such_file.js', status=404)
        self.app.get('/nf/_static_/no_such_tool/js/comments.js', status=404)
