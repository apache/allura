from allura.tests import TestController
from allura.tests import decorators as td


class TestToolListController(TestController):

    @td.with_wiki
    @td.with_tool('test', 'Wiki', 'wiki2')
    def test_default(self):
        """Test that list page contains a link to all tools of that type."""
        r = self.app.get('/p/test/_list/wiki')
        assert len(r.html.find('a', dict(href='/p/test/wiki/'))) == 1, r
        assert len(r.html.find('a', dict(href='/p/test/wiki2/'))) == 1, r
