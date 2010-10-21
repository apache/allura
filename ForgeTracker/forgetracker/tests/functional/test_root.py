import os, urllib
import Image, StringIO
import allura

from nose.tools import assert_true, assert_false, eq_
from formencode.variabledecode import variable_encode

from forgetracker.tests import TestController
from forgewiki import model as wm
from forgetracker import model as tm

# These are needed for faking reactor actions
import mock
from allura.lib import helpers as h
from allura.command import reactor
from allura.ext.search import search_main
from ming.orm.ormsession import ThreadLocalORMSession

class TestFunctionalController(TestController):

    def new_ticket(self, mount_point='/bugs/', **kw):
        response = self.app.get(mount_point + 'new/')
        form = response.forms[1]
        for k, v in kw.iteritems():
            form['ticket_form.%s' % k] = v
        resp = form.submit()
        if resp.status_int == 200:
            resp.showbrowser()
            assert 0, "form error?"
        return resp.follow()
    
    def test_bad_ticket_number(self):
        self.app.get('/bugs/input.project_user_select', status=404)

    def test_invalid_ticket(self):
        self.app.get('/bugs/2/', status=404)

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.new_ticket(summary=summary)
        assert_true(summary in ticket_view)
        assert 'class="artifact_unsubscribe' in ticket_view

    def test_new_with_milestone(self):
        ticket_view = self.new_ticket(summary='test new with milestone', **{'_milestone':'1.0'})
        assert 'Milestone' in ticket_view
        assert '1.0' in ticket_view
    
    def test_new_ticket_form(self):
        response = self.app.get('/bugs/new/')
        form = response.forms[1]
        form['ticket_form.summary'] = 'test new ticket form'
        form['ticket_form.assigned_to'] = 'test_admin'
        response = form.submit().follow()
        assert 'Test Admin' in response
    
    def test_two_trackers(self):
        summary = 'test two trackers'
        ticket_view = self.new_ticket('/doc-bugs/', summary=summary)
        assert_true(summary in ticket_view)
        index_view = self.app.get('/bugs/')
        assert_false(summary in index_view)
    
    def test_render_ticket(self):
        summary = 'test render ticket'
        ticket_view = self.new_ticket(summary=summary)
        ticket_view.mustcontain(summary, 'Discussion')
    
    def test_render_index(self):
        index_view = self.app.get('/bugs/')
        assert index_view.html.find('p',{'class':'light'}).string == '''Showing
  
    0
  
  results of 0 '''
    
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
            '_milestone':'',
            'assigned_to':'',
            'tags':'red,blue',
            'tags_old':'red,blue',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert_true('aaa' in response)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'',
            'tags':'red',
            'tags_old':'red',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert_true('zzz' in response)
    
    def test_ticket_label_unlabel(self):
        summary = 'test labeling and unlabeling a ticket'
        self.new_ticket(summary=summary)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'aaa',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'',
            'labels':'yellow,green',
            'labels_old':'yellow,green',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert_true('yellow' in response)
        assert_true('green' in response)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'',
            'labels':'yellow',
            'labels_old':'yellow',
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert_true('yellow' in response)
        # the following assert is no longer true since "green" is shown in changelog
        # assert_true('green' not in response)

    def test_new_attachment(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz'
        }, upload_files=[upload]).follow()
        assert_true(file_name in ticket_editor)
    
    def test_delete_attachment(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz'
        }, upload_files=[upload]).follow()
        assert_true(file_name in ticket_editor)
        req = self.app.get('/bugs/1/')
        file_link = req.html.findAll('form')[2].findAll('a')[7]
        print req.html.findAll('form')[2].findAll('a')
        assert file_link.string == file_name
        self.app.post(str(file_link['href']),{
            'delete':'True'
        })
        deleted_form = self.app.get('/bugs/1/')
        assert file_name not in deleted_form

    def test_new_text_attachment_content(self):
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz'
        }, upload_files=[upload]).follow()
        download = self.app.get(str(ticket_editor.html.findAll('form')[2].findAll('a')[7]['href']))
        assert_true(download.body == file_data)
    
    def test_new_image_attachment_content(self):
        h.set_context('test', 'bugs')
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'public','nf','images',file_name)
        file_data = file(file_path).read()
        upload = ('attachment', file_name, file_data)
        self.new_ticket(summary='test new attachment')
        ticket_editor = self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz'
        }, upload_files=[upload]).follow()
        ticket = tm.Ticket.query.find({'ticket_num':1}).first()
        filename = ticket.attachments.first().filename
    
        uploaded = Image.open(file_path)
        r = self.app.get('/bugs/1/attachment/'+filename)
        downloaded = Image.open(StringIO.StringIO(r.body))
        assert uploaded.size == downloaded.size
        r = self.app.get('/bugs/1/attachment/'+filename+'/thumb')
    
        thumbnail = Image.open(StringIO.StringIO(r.body))
        assert thumbnail.size == (100,100)
    
    def test_sidebar_static_page(self):
        response = self.app.get('/bugs/search/')
        assert 'Create Ticket' in response
        assert 'Related Artifacts' not in response
    
    def test_sidebar_ticket_page(self):
        summary = 'test sidebar logic for a ticket page'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'Create Ticket' in response
        assert 'Related Artifacts' not in response
        self.app.get('/wiki/aaa/update?title=aaa&text=&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all')
        self.new_ticket(summary='bbb')
        
        # Fake out updating the pages since reactor doesn't work with tests
        app = search_main.SearchApp
        cmd = reactor.ReactorCommand('reactor')
        cmd.args = [ os.environ.get('SF_SYSTEM_FUNC') and 'sandbox-test.ini' or 'test.ini' ]
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
        
        response = self.app.get('/p/test/bugs/1/')
        assert 'Related Artifacts' in response
        assert 'aaa' in response
        assert '#2' in response
    
    def test_ticket_view_editable(self):
        summary = 'test ticket view page can be edited'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert response.html.find('input', {'name': 'ticket_form.summary'})
        assert response.html.find('input', {'name': 'ticket_form.assigned_to'})
        assert response.html.find('textarea', {'name': 'ticket_form.description'})
        assert response.html.find('select', {'name': 'ticket_form.status'})
        assert response.html.find('select', {'name': 'ticket_form._milestone'})
        assert response.html.find('input', {'name': 'ticket_form.labels'})
        assert response.html.find('textarea', {'name': 'ticket_form.comment'})

    def test_assigned_to_nobody(self):
        summary = 'test default assignment'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'nobody' in str(response.html.find('div', {'class': 'column grid_3 ticket-assigned-to'}))
    
    def test_assign_ticket(self):
        summary = 'test assign ticket'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'test_admin',
            'tags':'',
            'tags_old':'',
            'labels':'',
            'labels_old':'',
            'comment': ''
        })
        response = self.app.get('/p/test/bugs/1/')
        assert 'nobody' in str(response.html.find('div', {'class': 'column grid_3 ticket-assigned-to'}))
        assert '<li><strong>summary</strong>: test assign ticket --&gt; zzz' in response
        assert '<li><strong>status</strong>: open --&gt; ccc' in response
    
    def test_custom_fields(self):
        params = dict(
            custom_fields=[
                dict(name='_priority', label='Priority', type='select',
                     options='normal urgent critical'),
                dict(name='_category', label='Category', type='string',
                     options='')],
            open_status_names='aa bb',
            closed_status_names='cc',
            )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        kw = {'custom_fields._priority':'normal',
              'custom_fields._category':'helloworld'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw)
        assert 'Priority:' in ticket_view
        assert 'normal' in ticket_view
    
    def test_custom_field_update_comments(self):
        params = dict(
            custom_fields=[
                dict(label='Number', type='number', options='')],
            open_status_names='aa bb',
            closed_status_names='cc',
            )
        r = self.app.post('/admin/bugs/set_custom_fields',
                          params=variable_encode(params))
        kw = {'custom_fields._number':''}
        ticket_view = self.new_ticket(summary='test custom fields', **kw)
        assert '<strong>custom_field__number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket',params={
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaa',
            'assigned_to':'',
            'tags':'',
            'tags_old':'',
            'labels':'',
            'labels_old':'',
            'custom_fields._number':'',
            'comment': ''
        }).follow()
        assert '<strong>custom_field__number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket',params={
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaa',
            'assigned_to':'',
            'tags':'',
            'tags_old':'',
            'labels':'',
            'labels_old':'',
            'custom_fields._number':4,
            'comment': ''
        }).follow()
        assert '<strong>custom_field__number</strong>:  --&gt;' in ticket_view

    def test_milestone_names(self):
        self.app.post('/admin/bugs/set_custom_fields', {
            'milestone_names': 'aaa bbb ccc',
            'open_status_names': 'aa bb',
            'closed_status_names': 'cc',
            'custom_fields': {}
        })
        self.new_ticket(summary='test milestone names')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaa',
            'assigned_to':'',
            'tags':'',
            'tags_old':'',
            'labels':'',
            'labels_old':'',
            'comment': ''
        })
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert 'aaa' in ticket_view
        assert '<li><strong>summary</strong>: test milestone names --&gt; zzz' in ticket_view

    def test_subtickets(self):
        # create two tickets
        self.new_ticket(summary='test superticket')
        self.new_ticket(summary='test subticket')
        h.set_context('test', 'bugs')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        super = tm.Ticket.query.get(ticket_num=1)
        sub = tm.Ticket.query.get(ticket_num=2)
    
        # make one ticket a subticket of the other
        sub.set_as_subticket_of(super._id)
        ThreadLocalORMSession.flush_all()
    
        # get a view on the first ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Supertask' not in ticket_view
        assert '[#2]' in ticket_view
 
        # get a view on the second ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/p/test/bugs/2/')
        assert 'Supertask' in ticket_view
        assert '[#1]' in ticket_view
    
    def test_custom_sums(self):
        # setup a custom sum field
        r = self.app.post('/admin/bugs/set_custom_fields', {
            'custom_fields-0.label': 'days',
            'custom_fields-0.type': 'sum',
            'custom_fields-0.sum': '',
            'custom_fields-0.milestones': '',
            'custom_fields-0.options': '',
            'open_status_names': 'aa bb',
            'closed_status_names': 'cc',
            'milestone_names':'' })
        # create three tickets
        kw = {'custom_fields._days':0}
        self.new_ticket(summary='test superticket', **kw)
        self.new_ticket(summary='test subticket-1', **kw)
        self.new_ticket(summary='test subticket-2', **kw)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
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
        ThreadLocalORMSession.close_all()
    
        # get a view on the first ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Days' in ticket_view
        assert '6.5' in ticket_view
    
    def test_edit_all_button(self):
        response = self.app.get('/p/test/bugs/search/')
        assert 'Edit All' not in response

    def test_new_ticket_validation(self):
        summary = 'ticket summary'
        response = self.app.get('/bugs/new/')
        assert not response.html.find('div', {'class':'error'})
        form = response.forms[1]
        # try submitting with no summary set and check for error message
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert (error_message.string == 'You must provide a Title' or \
                error_message.string == 'Missing value')
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.forms[1]['ticket_form.summary'] = summary
        success = error_form.forms[1].submit().follow().html
        assert success.findAll('form')[2].get('action') == '/p/test/bugs/1/update_ticket_from_widget'
        assert success.find('input', {'name':'ticket_form.summary'})['value'] == summary

    def test_edit_ticket_validation(self):
        old_summary = 'edit ticket test'
        new_summary = "new summary"
        self.new_ticket(summary=old_summary)
        response = self.app.get('/bugs/1/')
        # check that existing form is valid
        assert response.html.find('input', {'name':'ticket_form.summary'})['value'] == old_summary
        assert not response.html.find('div', {'class':'error'})
        form = response.forms[2]
        # try submitting with no summary set and check for error message
        form['ticket_form.summary'] = ""
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert error_message.string == 'You must provide a Title'
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.forms[2]['ticket_form.summary'] = new_summary
        r = error_form.forms[2].submit()
        assert r.status_int == 302, r.showbrowser()
        success = r.follow().html
        assert success.findAll('form')[2].get('action') == '/p/test/bugs/1/update_ticket_from_widget'
        assert success.find('input', {'name':'ticket_form.summary'})['value'] == new_summary

#   def test_home(self):
#       self.new_ticket(summary='test first ticket')
#       self.new_ticket(summary='test second ticket')
#       self.new_ticket(summary='test third ticket')
#       response = self.app.get('/p/test/bugs/')
#       assert '[#3] test third ticket' in response

#   def test_search(self):
#       self.new_ticket(summary='test first ticket')
#       self.new_ticket(summary='test second ticket')
#       self.new_ticket(summary='test third ticket')
#       response = self.app.get('/p/test/bugs/search/?q=!status%3Aclosed')
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

    def test_saved_search_labels_truncated(self):
        r = self.app.post('/admin/bugs/bins/save_bin',{
            'bin_form.summary': 'This is not too long.',
            'bin_form.terms': 'aaa',
            'bin_form.old_summary': '',
            'bin_form.sort': ''}).follow()
        sidebar_contains(r, 'This is not too long.')
        r = self.app.post('/admin/bugs/bins/save_bin',{
            'bin_form.summary': 'This will be truncated because it is too long to show in the sidebar without being ridiculous.',
            'bin_form.terms': 'aaa',
            'bin_form.old_summary': '',
            'bin_form.sort': ''}).follow()
        sidebar_contains(r, 'This will be truncated because it is too long to show in the sidebar ...')

    def test_edit_saved_search(self):
        r = self.app.post('/admin/bugs/bins/save_bin',{
            'bin_form.summary': 'Original',
            'bin_form.terms': 'aaa',
            'bin_form.old_summary': '',
            'bin_form.sort': ''}).follow()
        sidebar_contains(r, 'Original')
        not sidebar_contains(r, 'New')
        r = self.app.post('/admin/bugs/bins/save_bin',{
            'bin_form.summary': 'New',
            'bin_form.terms': 'aaa',
            'bin_form.old_summary': 'Original',
            'bin_form.sort': ''}).follow()
        sidebar_contains(r, 'New')
        not sidebar_contains(r, 'Original')


def sidebar_contains(response, text):
    sidebar_menu = response.html.find('div', attrs={'id': 'sidebar'})
    return text in str(sidebar_menu)

