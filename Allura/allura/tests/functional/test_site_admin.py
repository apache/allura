import json

from allura import model as M
from allura.tests import TestController
from allura.lib.decorators import task

class TestSiteAdmin(TestController):

    def test_access(self):
        r = self.app.get('/nf/admin/', extra_environ=dict(
                username='test-user'), status=403)

        r = self.app.get('/nf/admin/', extra_environ=dict(
                username='*anonymous'), status=302)
        r = r.follow()
        assert 'Login' in r

    def test_home(self):
        r = self.app.get('/nf/admin/', extra_environ=dict(
                username='root'))
        assert 'Forge Site Admin' in r.html.find('h2',{'class':'dark title'}).contents[0]
        stats_table = r.html.find('table')
        cells = stats_table.findAll('td')
        assert cells[0].contents[0] == 'Adobe', cells[0].contents[0]

    def test_performance(self):
        r = self.app.get('/nf/admin/stats', extra_environ=dict(
                username='test-user'), status=403)
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

    def test_tickets_access(self):
        r = self.app.get('/nf/admin/api_tickets', extra_environ=dict(
                username='test-user'), status=403)

    def test_new_projects_access(self):
        self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='test_user'), status=403)
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
            username='*anonymous'), status=302).follow()
        assert 'Login' in r

    def test_new_projects(self):
        r = self.app.get('/nf/admin/new_projects', extra_environ=dict(
                username='root'))
        headers = r.html.find('table').findAll('th')
        assert headers[1].contents[0] == 'Created'
        assert headers[2].contents[0] == 'Shortname'
        assert headers[3].contents[0] == 'Name'
        assert headers[4].contents[0] == 'Short description'
        assert headers[5].contents[0] == 'Summary'
        assert headers[6].contents[0] == 'Deleted?'
        assert headers[7].contents[0] == 'Homepage'
        assert headers[8].contents[0] == 'Admins'

    def test_reclone_repo_access(self):
        r = self.app.get('/nf/admin/reclone_repo', extra_environ=dict(
            username='*anonymous'), status=302).follow()
        assert 'Login' in r

    def test_reclone_repo(self):
        r = self.app.get('/nf/admin/reclone_repo')
        assert 'Reclone repository' in r

    def test_reclone_repo_default_value(self):
        r = self.app.get('/nf/admin/reclone_repo')
        assert 'value="p"' in r

    def test_task_list(self):
        r = self.app.get('/nf/admin/task_manager', extra_environ=dict(username='*anonymous'), status=302)
        import math
        task = M.MonQTask.post(math.ceil, (12.5,))
        r = self.app.get('/nf/admin/task_manager?page_num=1')
        assert 'math.ceil' in r, r

    def test_task_view(self):
        import math
        task = M.MonQTask.post(math.ceil, (12.5,))
        url = '/nf/admin/task_manager/view/%s' % task._id
        r = self.app.get(url, extra_environ=dict(username='*anonymous'), status=302)
        r = self.app.get(url)
        assert 'math.ceil' in r, r

    def test_task_new(self):
        r = self.app.get('/nf/admin/task_manager/new')
        assert 'New Task' in r, r

    def test_task_create(self):
        project = M.Project.query.get(shortname='test')
        app = project.app_instance('admin')
        user = M.User.by_username('root')

        task_args = dict(
                args=['foo'],
                kwargs=dict(bar='baz'))

        r = self.app.post('/nf/admin/task_manager/create', params=dict(
            task='allura.tests.functional.test_site_admin.test_task',
            task_args=json.dumps(task_args),
            user='root',
            path='/p/test/admin',
            ), status=302)
        task = M.MonQTask.query.find({}).sort('_id', -1).next()
        assert str(task._id) in r.location
        assert task.context['project_id'] == project._id
        assert task.context['app_config_id'] == app.config._id
        assert task.context['user_id'] == user._id
        assert task.args == task_args['args']
        assert task.kwargs == task_args['kwargs']

    def test_task_doc(self):
        r = self.app.get('/nf/admin/task_manager/task_doc', params=dict(
            task_name='allura.tests.functional.test_site_admin.test_task'))
        assert json.loads(r.body)['doc'] == 'test_task doc string'


@task
def test_task(*args, **kw):
    """test_task doc string"""
    pass
