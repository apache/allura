from pyforge.tests import TestController

class TestStatic(TestController):

    def test_static_controller(self):
        self.app.get('/nf/hello_forge/js/comments.js')
        self.app.get('/nf/hello_forge/js/no_such_file.js', status=404)
        self.app.get('/nf/no_such_tool/js/comments.js', status=404)
