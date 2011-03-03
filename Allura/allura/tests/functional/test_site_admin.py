import os, allura

from allura.tests import TestController


class TestSiteAdmin(TestController):

    def test_home(self):
        r = self.app.get('/nf/admin/', extra_environ=dict(
                username='root'))
        assert 'Forge Site Admin' in r.html.find('h2',{'class':'dark title'}).contents[0]
        stats_table = r.html.find('table')
        cells = stats_table.findAll('td')
        assert cells[0].contents[0] == 'Users'

    def test_performance(self):
        r = self.app.get('/nf/admin/stats', extra_environ=dict(
                username='root'))
        assert 'Forge Site Admin' in r.html.find('h2',{'class':'dark title'}).contents[0]
        stats_table = r.html.find('table')
        headers = stats_table.findAll('th')
        assert headers[0].contents[0] == 'Url'
        assert headers[1].contents[0] == 'Ming'
        assert headers[2].contents[0] == 'Mongo'
        assert headers[3].contents[0] == 'Render'
        assert headers[4].contents[0] == 'Template'
        assert headers[5].contents[0] == 'Total Time'

    def test_cpa(self):
        r = self.app.get('/nf/admin/cpa_stats', extra_environ=dict(
                username='root'))
        assert 'Forge Site Admin' in r.html.find('h2',{'class':'dark title'}).contents[0]
        stats_table = r.html.find('table')
        headers = stats_table.findAll('th')
        assert headers[0].contents[0] == 'Tool Name'
        assert headers[1].contents[0] == 'Class Name'
        assert headers[2].contents[0] == 'Create'
        assert headers[3].contents[0] == 'Modify'
        assert headers[4].contents[0] == 'Delete'
