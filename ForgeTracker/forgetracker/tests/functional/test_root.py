import os, urllib

from nose.tools import assert_true, assert_false
from forgetracker.tests import TestController
from pyforge import model
from forgewiki import model as wm
from forgetracker import model as tm

# These are needed for faking reactor actions
import mock
from pyforge.lib import helpers as h
from pyforge.command import reactor
from pyforge.ext.search import search_main
from ming.orm.ormsession import ThreadLocalORMSession


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

    def test_render_help(self):
        summary = 'test render help'
        r = self.app.get('/bugs/help')
        assert_true('Tracker Help' in r)

    def test_render_markdown_syntax(self):
        summary = 'test render markdown syntax'
        r = self.app.get('/bugs/markdown_syntax')
        assert_true('Markdown Syntax' in r)

    def test_ticket_tag_untag(self):
        summary = 'test tagging and untagging a ticket'
        self.new_ticket(summary)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'aaa',
            'description':'bbb',
            'status':'ccc',
            'assigned_to':'',
            'tags':'red,blue',
            'tags_old':'red,blue'
        })
        response = self.app.get('/bugs/1/')
        assert_true('aaa' in response)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            'assigned_to':'',
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

    def test_sidebar_static_page(self):
        response = self.app.get('/bugs/search/')
        assert 'Create New Ticket' in response
        assert 'Update this Ticket' not in response
        assert 'Related Artifacts' not in response

    def test_sidebar_ticket_page(self):
        summary = 'test sidebar logic for a ticket page'
        self.new_ticket(summary)
        response = self.app.get('/projects/test/bugs/1/')
        assert 'Create New Ticket' in response
        assert 'Update this Ticket' in response
        assert 'Related Artifacts' not in response
        self.app.get('/Wiki/aaa/')
        self.new_ticket('bbb')
        
        # Fake out updating the pages since reactor doesn't work with tests
        app = search_main.SearchApp
        cmd = reactor.ReactorCommand('reactor')
        cmd.args = [ os.environ.get('SANDBOX') and 'sandbox-test.ini' or 'test.ini' ]
        cmd.options = mock.Mock()
        cmd.options.dry_run = True
        cmd.options.proc = 1
        configs = cmd.command()
        add_artifacts = cmd.route_audit('search', app.add_artifacts)
        del_artifacts = cmd.route_audit('search', app.del_artifacts)
        msg = mock.Mock()
        msg.ack = lambda:None
        msg.delivery_info = dict(routing_key='search.add_artifacts')
        h.set_context('test', 'wiki')
        a = wm.Page.query.find(dict(title='aaa')).first()
        a.text = '\n[bugs:#1]\n'
        msg.data = dict(project_id=a.project_id,
                        mount_point=a.app_config.options.mount_point,
                        artifacts=[a.dump_ref()])
        add_artifacts(msg.data, msg)
        b = tm.Ticket.query.find(dict(ticket_num=2)).first()
        b.description = '\n[#1]\n'
        msg.data = dict(project_id=b.project_id,
                        mount_point=b.app_config.options.mount_point,
                        artifacts=[b.dump_ref()])
        add_artifacts(msg.data, msg)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        
        response = self.app.get('/projects/test/bugs/1/')
        assert 'Related Artifacts' in response
        assert 'aaa' in response
        assert '#2' in response


    def test_assign_ticket(self):
        summary = 'test assign ticket'
        self.new_ticket(summary)
        response = self.app.get('/projects/test/bugs/1/edit/')
        assert 'nobody' in response.html.find('span', {'class': 'viewer ticket-assigned-to'}).string
        test_user = response.html.find(id="assigned_to").findAll('option')[1]
        test_user_id = test_user['value']
        test_user_name = test_user.string
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            'assigned_to':test_user_id,
            'tags':'',
            'tags_old':''
        })
        response = self.app.get('/projects/test/bugs/1/edit/')
        assert test_user_name in response.html.find('span', {'class': 'viewer ticket-assigned-to'}).find('a').string

    def test_custom_fields(self):
        spec = """[{"label":"Priority","type":"select","options":"normal urgent critical"},
                   {"label":"Category","type":"string","options":""}]"""
        spec = urllib.quote_plus(spec)
        self.app.post('/admin/bugs/set_custom_fields', { 'custom_fields': spec })
        ticket_view = self.new_ticket('test custom fields')
        assert 'Priority: normal' in ticket_view

    def test_subtickets(self):
        # create two tickets
        self.new_ticket('test superticket')
        self.new_ticket('test subticket')
        h.set_context('test', 'bugs')
        super = tm.Ticket.query.get(ticket_num=1)
        sub = tm.Ticket.query.get(ticket_num=2)

        # make one ticket a subticket of the other
        sub.set_as_subticket_of(super._id)
        ThreadLocalORMSession.flush_all()

        # get a view on the first ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/projects/test/bugs/1/')
        assert 'Supertask' not in ticket_view
        assert 'Ticket 2' in ticket_view

        # get a view on the second ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/projects/test/bugs/2/')
        assert 'Supertask' in ticket_view
        assert 'Ticket 1' in ticket_view

    def test_custom_sums(self):
        # setup a custom sum field
        spec = """[{"label":"Days","type":"sum","options":""}]"""
        spec = urllib.quote_plus(spec)
        self.app.post('/admin/bugs/set_custom_fields', { 'custom_fields': spec })

        # create three tickets
        self.new_ticket('test superticket')
        self.new_ticket('test subticket-1')
        self.new_ticket('test subticket-2')
        h.set_context('test', 'bugs')
        super = tm.Ticket.query.get(ticket_num=1)
        sub1 = tm.Ticket.query.get(ticket_num=2)
        sub2 = tm.Ticket.query.get(ticket_num=3)

        # set values for the custom sum
        sub1.custom_fields['_days'] = 4.5
        sub2.custom_fields['_days'] = 2.0

        # make two tickets a subtickets of the other
        sub1.set_as_subticket_of(super._id)
        sub2.set_as_subticket_of(super._id)
        ThreadLocalORMSession.flush_all()

        # get a view on the first ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/projects/test/bugs/1/')
        assert 'Days: 6.5' in ticket_view

    def test_edit_all_button(self):
        response = self.app.get('/projects/test/bugs/search/')
        assert 'Edit All' not in response
