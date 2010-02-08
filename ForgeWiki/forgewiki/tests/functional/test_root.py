from nose.tools import assert_true

from forgewiki.tests import TestController

#---------x---------x---------x---------x---------x---------x---------x
# RootController methods exposed:
#     index, new_page, search
# PageController methods exposed:
#     index, edit, history, diff, raw, revert, update
# CommentController methods exposed:
#     reply, delete

class TestRootController(TestController):
    def test_root_index(self):
        response = self.app.get('/Wiki/TEST/index')
        assert_true('TEST' in response)

    def test_root_markdown_syntax(self):
        response = self.app.get('/Wiki/markdown_syntax')
        assert_true('Markdown Syntax' in response)

    def test_root_browse_pages(self):
        response = self.app.get('/Wiki/browse')
        assert_true('Browse Pages' in response)

    def test_root_new_page(self):
        response = self.app.get('/Wiki/new_page?title=TEST')
        assert_true('TEST' in response)

    def test_root_new_search(self):
        response = self.app.get('/Wiki/TEST/index')
        response = self.app.get('/Wiki/search?q=TEST')
        assert_true('ForgeWiki Search' in response)

    def test_page_index(self):
        response = self.app.get('/Wiki/TEST/index/')
        assert_true('TEST' in response)

    def test_page_edit(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.post('/Wiki/TEST/edit')
        assert_true('TEST' in response)

    def test_page_history(self):
        response = self.app.get('/Wiki/TEST/history')
        assert_true('TEST' in response)

    def test_page_diff(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/revert?version=1')
        response = self.app.get('/Wiki/TEST/diff?v1=0&v2=0')
        assert_true('TEST' in response)

    def test_page_raw(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/raw')
        assert_true('TEST' in response)

    def test_page_revert_no_text(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/revert?version=1')
        assert_true('TEST' in response)

    def test_page_revert_with_text(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/update?text=sometext&tags=&tags_old=')
        response = self.app.get('/Wiki/TEST/revert?version=1')
        assert_true('TEST' in response)

    def test_page_update(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/update?text=sometext&tags=&tags_old=')
        assert_true('TEST' in response)

    def test_page_tag_untag(self):
        response = self.app.get('/Wiki/TEST/index/')
        response = self.app.get('/Wiki/TEST/update?text=sometext&tags=red,blue&tags_old=red,blue')
        assert_true('TEST' in response)
        response = self.app.get('/Wiki/TEST/update?text=sometext&tags=red&tags_old=red')
        assert_true('TEST' in response)

    def test_comment_reply(self):
        response = self.app.get('/Wiki/TEST/index')
        response = self.app.post('/Wiki/TEST/comments/reply?text=sometext')

#    def test_comment_delete(self):
#        response = self.app.get('/Wiki/TEST/index')
#        response = self.app.post('/Wiki/TEST/comments/reply?text=sometext')
#        response = self.app.post('/Wiki/TEST/comments/delete')

    def test_new_attachment(self):
        content = file(__file__).read()
        response = self.app.post('/wiki/TEST/attach', upload_files=[('file_info', 'test_root.py', content)])
        response = self.app.get('/wiki/TEST/')
        assert_true('test_root.py' in response)
