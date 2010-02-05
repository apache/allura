from nose.tools import assert_true, assert_false
from forgetracker.tests import TestController
from pyforge import model


class TestFunctionalController(TestController):

    def new_ticket(self, summary, mp='/bugs/'):
        response = self.app.get(mp + 'new/')
        form = response.form
        form['summary'] = summary
        return form.submit().follow()

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.new_ticket(summary)
        assert_true(summary in ticket_view)

    def test_two_trackers(self):
        summary = 'test two trackers'
        ticket_view = self.new_ticket(summary, '/doc_bugs/')
        assert_true(summary in ticket_view)
        index_view = self.app.get('/bugs/')
        assert_false(summary in index_view)

    def test_new_comment(self):
        self.new_ticket('test new comment')
        comment = 'comment testing new comment'
        self.app.post('/bugs/1/comments/reply', { 'text': comment })
        ticket_view = self.app.get('/bugs/1/')
        assert_true(comment in ticket_view)

    def test_render_ticket(self):
        summary = 'test render ticket'
        ticket_view = self.new_ticket(summary)
        ticket_view.mustcontain(summary, 'Comments', 'Make a comment')

    def test_render_index(self):
        summary = 'test render index'
        self.new_ticket(summary)
        index_view = self.app.get('/bugs/')
        assert_true(summary in index_view)

    def test_ticket_tag_untag(self):
        summary = 'test tagging and untagging a ticket'
        self.new_ticket(summary)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'aaa',
            'description':'bbb',
            'status':'ccc',
            'tags':'red,blue',
            'tags_old':'red,blue'
        })
        response = self.app.get('/bugs/1/')
        assert_true('aaa' in response)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            'tags':'red',
            'tags_old':'red'
        })
        response = self.app.get('/bugs/1/')
        assert_true('zzz' in response)

    def test_new_attachment(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('file_info', file_name, file_data)
        self.new_ticket('test new attachment')
        ticket_editor = self.app.post('/bugs/1/attach', upload_files=[upload]).follow()
        assert_true(file_name in ticket_editor)

    def test_new_attachment_content(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('file_info', file_name, file_data)
        self.new_ticket('test new attachment')
        ticket_editor = self.app.post('/bugs/1/attach', upload_files=[upload]).follow()
        download = ticket_editor.click(description=file_name)
        assert_true(download.body == file_data)
