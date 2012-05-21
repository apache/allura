import datetime

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import TestController
from allura import model as M

#---------x---------x---------x---------x---------x---------x---------x
# RootController methods exposed:
#     index, new_page, search
# PageController methods exposed:
#     index, edit, history, diff, raw, revert, update
# CommentController methods exposed:
#     reply, delete

class TestRootController(TestController):

    def _post(self, slug='', **kw):
        d = {
                'title':'My Post',
                'text':'Nothing to see here',
                'labels':'',
                'state':'published'}
        d.update(kw)
        r = self.app.post('/blog%s/save' % slug, params=d)
        return r

    def _blog_date(self):
        return datetime.datetime.utcnow().strftime('%Y/%m')

    def test_root_index(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/')
        assert 'Recent posts' in response
        assert 'Nothing to see here' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/',
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see Edit links
        assert 'Nothing to see here' in anon_r
        assert '/blog/%s/my-post/edit' % d not in anon_r

    def test_root_index_draft(self):
        self._post(state='draft')
        d = self._blog_date()
        response = self.app.get('/blog/')
        assert 'Recent posts' in response
        assert 'Nothing to see here' in response
        assert 'Draft' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/',
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see draft posts
        assert 'Nothing to see here' not in anon_r

    def test_root_new_post(self):
        response = self.app.get('/blog/new')
        assert '<option selected value="published">Published</option>' in response
        assert 'Enter your title here' in response

    def test_validation(self):
        r = self._post(title='')
        assert 'You must provide a Title' in r

    def test_root_new_search(self):
        self._post()
        response = self.app.get('/blog/search?q=see')
        assert 'Search' in response

    def test_paging(self):
        [self._post() for i in range(3)]
        r = self.app.get('/blog/?limit=1&page=0')
        assert 'Newer Entries' not in r
        assert 'Older Entries' in r
        r = self.app.get('/blog/?limit=1&page=1')
        assert 'Newer Entries' in r
        assert 'Older Entries' in r
        r = self.app.get('/blog/?limit=1&page=2')
        assert 'Newer Entries' in r
        assert 'Older Entries' not in r

    def test_discussion_admin(self):
        r = self.app.get('/blog/')
        r = self.app.get('/admin/blog/options', validate_chunk=True)
        assert 'Allow discussion/commenting on posts' in r
        # Turn discussion on
        r = self.app.post('/admin/blog/set_options',
                          params=dict(show_discussion='1'))
        self._post()
        d = self._blog_date()
        r = self.app.get('/blog/%s/my-post/' % d)
        assert '<div class="markdown_edit">' in r
        # Turn discussion off
        r = self.app.post('/admin/blog/set_options')
        r = self.app.get('/blog/%s/my-post/' % d)
        assert '<div class="markdown_edit">' not in r

    def test_post_index(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/' % d)
        assert 'Nothing to see here' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/%s/my-post/' % d,
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't see Edit links
        assert 'Nothing to see here' in anon_r
        assert '/blog/%s/my-post/edit' % d not in anon_r
        self.app.get('/blog/%s/no-my-post' % d, status=404)

    def test_post_index_draft(self):
        self._post(state='draft')
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/' % d)
        assert 'Nothing to see here' in response
        assert 'Draft' in response
        assert '/blog/%s/my-post/edit' % d in response
        anon_r = self.app.get('/blog/%s/my-post/' % d,
                              extra_environ=dict(username='*anonymous'))
        # anonymous user can't get to draft posts
        assert 'Nothing to see here' not in anon_r

    def test_post_edit(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/edit' % d)
        assert 'Nothing' in response
        # anon users can't edit
        response = self.app.get('/blog/%s/my-post/edit' % d,
                                extra_environ=dict(username='*anonymous'))
        assert 'Nothing' not in response

    def test_post_history(self):
        self._post()
        d = self._blog_date()
        self._post('/%s/my-post' % d)
        self._post('/%s/my-post' % d)
        response = self.app.get('/blog/%s/my-post/history' % d)
        assert 'My Post' in response
        # two revisions are shown
        assert '2 by Test Admin' in response
        assert '1 by Test Admin' in response
        self.app.get('/blog/%s/my-post?version=1' % d)
        self.app.get('/blog/%s/my-post?version=foo' % d, status=404)

    def test_post_diff(self):
        self._post()
        d = self._blog_date()
        self._post('/%s/my-post' % d, text='sometext')
        self.app.post('/blog/%s/my-post/revert' % d, params=dict(version='1'))
        response = self.app.get('/blog/%s/my-post/' % d)
        response = self.app.get('/blog/%s/my-post/diff?v1=0&v2=0' % d)
        assert 'My Post' in response

    def test_feeds(self):
        self.app.get('/blog/feed.rss')
        self.app.get('/blog/feed.atom')

    def test_post_feeds(self):
        self._post()
        d = self._blog_date()
        response = self.app.get('/blog/%s/my-post/feed.rss' % d)
        assert 'Nothing to see' in response
        response = self.app.get('/blog/%s/my-post/feed.atom' % d)
        assert 'Nothing to see' in response

    def test_related_artifacts(self):
        self._post(title='one')
        d = self._blog_date()
        self._post(title='two', text='[blog:%s/one]' % d)
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r= self.app.get('/blog/%s/one/' % d)
        assert 'Related' in r
        assert 'Blog Post: %s/two' % d in r
