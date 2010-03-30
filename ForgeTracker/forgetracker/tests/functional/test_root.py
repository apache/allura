import os, urllib
import Image, StringIO
import pyforge

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

    def new_ticket(self, mount_point='/bugs/', **kw):
        response = self.app.get(mount_point + 'new/')
        form = response.form
        for k, v in kw.iteritems():
            form['ticket_form.%s' % k] = v
        return form.submit().follow()
    
    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.new_ticket(summary=summary)
        assert_true(summary in ticket_view)
    
    def test_new_with_milestone(self):
        tm.Globals.milestone_names = 'sprint-9 sprint-10 sprint-11'
        ticket_view = self.new_ticket(summary='test new with milestone', milestone='sprint-10')
        assert 'Milestone' in ticket_view
        assert 'sprint-10' in ticket_view
    
    def test_new_ticket_form(self):
        response = self.app.get('/bugs/new/')
        test_user = response.html.find(id="ticket_form.assigned_to").findAll('option')[1]
        test_user_id = test_user['value']
        test_user_name = test_user.string
        form = response.form
        form['ticket_form.summary'] = 'test new ticket form'
        form['ticket_form.assigned_to'] = test_user_id
        response = form.submit().follow()
        assert test_user_name in response
    
    def test_two_trackers(self):
        summary = 'test two trackers'
        ticket_view = self.new_ticket('/doc_bugs/', summary=summary)
        assert_true(summary in ticket_view)
        index_view = self.app.get('/bugs/')
        assert_false(summary in index_view)
    
    def test_render_ticket(self):
        summary = 'test render ticket'
        ticket_view = self.new_ticket(summary=summary)
        ticket_view.mustcontain(summary, 'Discussion', 'No posts found')
    
    def test_render_index(self):
        summary = 'test render index'
        self.new_ticket(summary=summary)
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
        self.new_ticket(summary=summary)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'aaa',
            'description':'bbb',
            'status':'ccc',
            'milestone':'',
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
            'milestone':'',
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
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/attach', upload_files=[upload]).follow()
        assert_true(file_name in ticket_editor)
    
    def test_new_text_attachment_content(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('file_info', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/attach', upload_files=[upload]).follow()
        download = ticket_editor.click(description=file_name)
        assert_true(download.body == file_data)
    
    def test_new_image_attachment_content(self):
        h.set_context('test', 'bugs')
        file_name = 'adobe_header.png'
        file_path = os.path.join(pyforge.__path__[0],'public','images',file_name)
        file_data = file(file_path).read()
        upload = ('file_info', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        self.app.post('/bugs/1/attach', upload_files=[upload])
        ticket = tm.Ticket.query.find({'ticket_num':1}).first()
        filename = ticket.attachments.first().filename
    
        uploaded = Image.open(file_path)
        r = self.app.get('/bugs/1/attachment/'+filename)
        downloaded = Image.open(StringIO.StringIO(r.body))
        assert uploaded.size == downloaded.size
        r = self.app.get('/bugs/1/attachment/'+filename+'/thumb')
    
        thumbnail = Image.open(StringIO.StringIO(r.body))
        assert thumbnail.size == (101,101)
    
    def test_sidebar_static_page(self):
        response = self.app.get('/bugs/search/')
        assert 'Create New Ticket' in response
        assert 'Update this Ticket' not in response
        assert 'Related Artifacts' not in response
    
    def test_sidebar_ticket_page(self):
        summary = 'test sidebar logic for a ticket page'
        self.new_ticket(summary=summary)
        response = self.app.get('/projects/test/bugs/1/')
        assert 'Create New Ticket' in response
        assert 'Update this Ticket' in response
        assert 'Related Artifacts' not in response
        self.app.get('/Wiki/aaa/')
        self.new_ticket(summary='bbb')
        
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
    
    def test_ticket_view_editable(self):
        summary = 'test ticket view page can be edited'
        self.new_ticket(summary=summary)
        response = self.app.get('/projects/test/bugs/1/')
        assert response.html.find('input', {'name': 'summary'})
        assert response.html.find('select', {'name': 'assigned_to'})
        assert response.html.find('textarea', {'name': 'description'})
        assert response.html.find('select', {'name': 'status'})
        assert response.html.find('select', {'name': 'milestone'})
        assert response.html.find('input', {'name': 'tags'})
    
    def test_assign_ticket(self):
        summary = 'test assign ticket'
        self.new_ticket(summary=summary)
        response = self.app.get('/projects/test/bugs/1/')
        assert 'nobody' in response.html.find('span', {'class': 'ticket-assigned-to viewer'}).string
        test_user = response.html.find(id="assigned_to").findAll('option')[1]
        test_user_id = test_user['value']
        test_user_name = test_user.string
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            'milestone':'',
            'assigned_to':test_user_id,
            'tags':'',
            'tags_old':''
        })
        response = self.app.get('/projects/test/bugs/1/')
        assert test_user_name in response.html.find('span', {'class': 'ticket-assigned-to viewer'}).find('a').string
    
    def test_custom_fields(self):
        spec = """[{"label":"Priority","type":"select","options":"normal urgent critical"},
                   {"label":"Category","type":"string","options":""}]"""
        spec = urllib.quote_plus(spec)
        r = self.app.post('/admin/bugs/set_custom_fields', { 'custom_fields': spec })
        ticket_view = self.new_ticket(summary='test custom fields')
        assert 'Priority:' in ticket_view
        assert 'normal' in ticket_view
    
    def test_milestone_names(self):
        self.app.post('/admin/bugs/set_milestone_names', { 'milestone_names': 'aaa bbb ccc' })
        self.new_ticket(summary='test milestone names')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            'milestone':'aaa',
            'assigned_to':'',
            'tags':'',
            'tags_old':''
        })
        ticket_view = self.app.get('/projects/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert 'aaa' in ticket_view
    
    def test_subtickets(self):
        # create two tickets
        self.new_ticket(summary='test superticket')
        self.new_ticket(summary='test subticket')
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
        self.new_ticket(summary='test superticket')
        self.new_ticket(summary='test subticket-1')
        self.new_ticket(summary='test subticket-2')
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
        assert 'Days' in ticket_view
        assert '6.5' in ticket_view
    
    def test_edit_all_button(self):
        response = self.app.get('/projects/test/bugs/search/')
        assert 'Edit All' not in response

    def test_new_ticket_validation(self):
        summary = 'ticket summary'
        response = self.app.get('/bugs/new/')
        assert not response.html.find('div', {'class':'error'})
        form = response.form
        # try submitting with no summary set and check for error message
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert error_message.string == 'Please enter a value'
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.form['ticket_form.summary'] = summary
        success = error_form.form.submit().follow().html
        assert success.find('form').get('action') == '/projects/test/bugs/1/update_ticket'
        assert success.find('input', {'name':'summary'}).get('value') == summary

    def test_edit_ticket_validation(self):
        old_summary = 'edit ticket test'
        new_summary = "new summary"
        self.new_ticket(summary=old_summary)
        response = self.app.get('/bugs/1/edit/')
        # check that existing form is valid
        assert response.html.find('input', {'name':'ticket_form.summary'}).get('value') == old_summary
        assert not response.html.find('div', {'class':'error'})
        form = response.forms[0]
        # try submitting with no summary set and check for error message
        form['ticket_form.summary'] = ""
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert error_message.string == 'Please enter a value'
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.forms[0]['ticket_form.summary'] = new_summary
        success = error_form.forms[0].submit().follow().html
        assert success.find('form').get('action') == '/projects/test/bugs/1/update_ticket'
        assert success.find('input', {'name':'summary'}).get('value') == new_summary

#   def test_home(self):
#       self.new_ticket(summary='test first ticket')
#       self.new_ticket(summary='test second ticket')
#       self.new_ticket(summary='test third ticket')
#       response = self.app.get('/projects/test/bugs/')
#       assert '[#3] test third ticket' in response

#   def test_search(self):
#       self.new_ticket(summary='test first ticket')
#       self.new_ticket(summary='test second ticket')
#       self.new_ticket(summary='test third ticket')
#       response = self.app.get('/projects/test/bugs/search/?q=!status%3Aclosed')
#       assert '3 results' in response
#       assert '[#3] test third ticket' in response

    def test_touch(self):
        self.new_ticket(summary='test touch')
        h.set_context('test', 'bugs')
        ticket = tm.Ticket.query.get(ticket_num=1)
        old_date = ticket.mod_date
        ticket.summary = 'changing the summary'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        ticket = tm.Ticket.query.get(ticket_num=1)
        new_date = ticket.mod_date
        assert new_date > old_date
