import tg
import pkg_resources
from pylons import c
from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import helpers as h
from alluratest.controller import TestController

class TestRootController(TestController):

    def setUp(self):
        TestController.setUp(self)
        h.set_context('test', 'src-git')
        repo_dir = pkg_resources.resource_filename(
            'forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit.git'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'src-git')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_fork(self):
        r = self.app.post('/src-git/fork', params=dict(
            project_name='test2',
            to_name='code'))
        cloned_from = c.app.repo
        with h.push_context('test2', 'code'):
            c.app.repo.init_as_clone(
                    cloned_from.full_fs_path,
                    cloned_from.app.config.script_name(),
                    cloned_from.full_fs_path)
        r = self.app.get('/p/test2/code').follow().follow().follow()
        assert 'Clone of' in r
        r = self.app.get('/src-git/').follow().follow()
        assert 'Forks' in r

    def test_merge_request(self):
        r = self.app.post('/src-git/fork', params=dict(
            project_name='test2',
            to_name='code'))
        cloned_from = c.app.repo
        with h.push_context('test2', 'code'):
            c.app.repo.init_as_clone(
                    cloned_from.full_fs_path,
                    cloned_from.app.config.script_name(),
                    cloned_from.full_fs_path)
        r = self.app.get('/p/test2/code/').follow().follow()
        assert 'Request Merge' in r
        # Request Merge button only visible to repo admins
        kw = dict(extra_environ=dict(username='test-user'))
        r = self.app.get('/p/test2/code/', **kw).follow(**kw).follow(**kw)
        assert 'Request Merge' not in r, r
        # Request merge controller action only permitted for repo admins
        r = self.app.get('/p/test2/code/request_merge', status=403, **kw)
        r = self.app.get('/p/test2/code/request_merge')
        assert 'Request merge' in r
        # Merge request detail view
        r = r.forms[0].submit().follow()
        assert 'would like you to merge' in r
        mr_num = r.request.url.split('/')[-2]
        # Merge request list view
        r = self.app.get('/p/test/src-git/merge-requests/')
        assert 'href="%s/"' % mr_num in r
        # Merge request status update
        r = self.app.post('/p/test/src-git/merge-requests/%s/save' % mr_num,
                          params=dict(status='rejected')).follow()
        assert 'Merge Request #%s:  (rejected)' % mr_num in r, r

    def test_index(self):
        resp = self.app.get('/src-git/').follow().follow()
        assert 'git://' in resp

    def test_index_empty(self):
        self.app.get('/git/')

    def test_commit_browser(self):
        resp = self.app.get('/src-git/commit_browser')
        commit_script = resp.html.findAll('script')[1].contents[0]
        assert "var max_row = 4;" in commit_script
        assert "var next_column = 1;" in commit_script
        assert '{"column": 0, "series": 0, "url": "/p/test/src-git/ci/df30427c488aeab84b2352bdf88a3b19223f9d7a/", "parents": ["6a45885ae7347f1cac5103b0050cc1be6a1496c8"], "message": "Add README", "row": 1}' in commit_script

    def test_log(self):
        resp = self.app.get('/src-git/ref/master~/log/')

    def test_tags(self):
        resp = self.app.get('/src-git/ref/master~/tags/')

    def _get_ci(self):
        r = self.app.get('/src-git/ref/master:/')
        resp = r.follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith('/p/test/src-git/ci/'):
                return tag['href']
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Rick' in resp, resp.showbrowser()

    def test_feed(self):
        assert 'Add README' in self.app.get('/feed')

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get(ci + 'tree/')
        assert 'README' in resp, resp.showbrowser()
        links = [ a.get('href') for a in resp.html.findAll('a') ]
        assert 'README' in links, resp.showbrowser()
        assert 'README/' not in links, resp.showbrowser()

    def test_tree_extra_params(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/?format=raw')
        assert 'README' in resp, resp.showbrowser()

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README')
        assert 'README' in resp.html.find('h2',{'class':'dark title'}).contents[2]
        content = str(resp.html.find('div',{'class':'clip grid-19'}))
        assert 'This is readme' in content, content

    def test_invalid_file(self):
        ci = self._get_ci()
        self.app.get(ci + 'tree/READMEz', status=404)

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert 'readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()

    def test_refresh(self):
        notification = M.Notification.query.find(
            dict(subject='[test:src-git] 4 new commits to test Git')).first()
        domain = '.'.join(reversed(c.app.url[1:-1].split('/'))).replace('_', '-')
        common_suffix = tg.config.get('forgemail.domain', '.sourceforge.net')
        email = 'noreply@%s%s' % (domain, common_suffix)
        assert email in notification['reply_to_address']

    def test_file_force_display(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?force=True')
        content = str(resp.html.find('div',{'class':'clip grid-19'}))
        assert '<pre>This is readme' in content, content
        assert '</pre>' in content, content
