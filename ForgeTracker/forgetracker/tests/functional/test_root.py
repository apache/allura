# -*- coding: utf-8 -*-
import os
import Image, StringIO
import allura

from mock import patch
from nose.tools import assert_true, assert_false, assert_equal
from formencode.variabledecode import variable_encode

from alluratest.controller import TestController
from allura import model as M
from forgewiki import model as wm
from forgetracker import model as tm

from allura.lib import helpers as h
from allura.tests import decorators as td
from ming.orm.ormsession import ThreadLocalORMSession

class TrackerTestController(TestController):
    def setUp(self):
        super(TrackerTestController, self).setUp()
        self.setup_with_tools()

    @td.with_tracker
    def setup_with_tools(self):
        pass

    def new_ticket(self, mount_point='/bugs/', **kw):
        response = self.app.get(mount_point + 'new/')
        form = response.forms[1]
        for k, v in kw.iteritems():
            form['ticket_form.%s' % k] = v
        resp = form.submit()
        assert resp.status_int != 200, resp
        return resp

class TestMilestones(TrackerTestController):
    def test_milestone_list(self):
        r = self.app.get('/bugs/milestones')
        assert '1.0' in r, r.showbrowser()

    def test_milestone_list_progress(self):
        self.new_ticket(summary='foo', _milestone='1.0')
        self.new_ticket(summary='bar', _milestone='1.0', status='closed')
        r = self.app.get('/bugs/milestones')
        assert '1 / 2' in r, r.showbrowser()

class TestFunctionalController(TrackerTestController):
    def test_bad_ticket_number(self):
        self.app.get('/bugs/input.project_user_select', status=404)

    def test_invalid_ticket(self):
        self.app.get('/bugs/2/', status=404)

    def test_new_ticket(self):
        summary = 'test new ticket'
        ticket_view = self.new_ticket(summary=summary).follow()
        assert_true(summary in ticket_view)
        assert 'class="artifact_subscribe' in ticket_view

    def test_new_with_milestone(self):
        ticket_view = self.new_ticket(summary='test new with milestone', **{'_milestone':'1.0'}).follow()
        assert 'Milestone' in ticket_view
        assert '1.0' in ticket_view

    def test_milestone_count(self):
        self.new_ticket(summary='test new with milestone', **{'_milestone':'1.0'})
        self.new_ticket(summary='test new with milestone', **{'_milestone':'1.0',
                                                              'private': '1'})
        r = self.app.get('/bugs/')
        assert '<small>2</small>' in r
        # Private tickets shouldn't be included in counts if user doesn't
        # have read access to private tickets.
        r = self.app.get('/bugs/', extra_environ=dict(username='*anonymous'))
        assert '<small>1</small>' in r

    def test_milestone_progress(self):
        self.new_ticket(summary='Ticket 1', **{'_milestone':'1.0'})
        self.new_ticket(summary='Ticket 2', **{'_milestone':'1.0',
                                               'status': 'closed',
                                               'private': '1'}).follow()
        r = self.app.get('/bugs/milestone/1.0/')
        assert '1 / 2' in r
        # Private tickets shouldn't be included in counts if user doesn't
        # have read access to private tickets.
        r = self.app.get('/bugs/milestone/1.0/',
                         extra_environ=dict(username='*anonymous'))
        assert '0 / 1' in r

    def test_new_ticket_form(self):
        response = self.app.get('/bugs/new/')
        form = response.forms[1]
        form['ticket_form.summary'] = 'test new ticket form'
        form['ticket_form.assigned_to'] = 'test_admin'
        response = form.submit().follow()
        assert 'Test Admin' in response

    def test_private_ticket(self):
        ticket_view = self.new_ticket(summary='Public Ticket').follow()
        assert_true('<label class="simple">Private:</label> No' in ticket_view)
        ticket_view = self.new_ticket(summary='Private Ticket',
                                      private=True).follow()
        assert_true('<label class="simple">Private:</label> Yes' in ticket_view)
        M.MonQTask.run_ready()
        # Creator sees private ticket on list page...
        index_response = self.app.get('/p/test/bugs/')
        assert '2 results' in index_response
        assert 'Public Ticket' in index_response
        assert 'Private Ticket' in index_response
        # ...and in search results.
        search_response = self.app.get('/p/test/bugs/search/?q=ticket')
        assert '2 results' in search_response
        assert 'Private Ticket' in search_response
        # Unauthorized user doesn't see private ticket on list page...
        env = dict(username='*anonymous')
        r = self.app.get('/p/test/bugs/', extra_environ=env)
        assert '1 results' in r
        assert 'Private Ticket' not in r
        # ...or in search results...
        r = self.app.get('/p/test/bugs/search/?q=ticket', extra_environ=env)
        assert '1 results' in r
        assert 'Private Ticket' not in r
        # ...and can't get to the private ticket directly.
        r = self.app.get(ticket_view.request.url, extra_environ=env)
        assert 'Private Ticket' not in r
        # ... and it doesn't appear in the feed
        r = self.app.get('/p/test/bugs/feed.atom')
        assert 'Private Ticket' not in r

    @td.with_tool('test', 'Tickets', 'doc-bugs')
    def test_two_trackers(self):
        summary = 'test two trackers'
        ticket_view = self.new_ticket('/doc-bugs/', summary=summary, _milestone='1.0').follow()
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        assert_true(summary in ticket_view)
        index_view = self.app.get('/doc-bugs/')
        assert_true(summary in index_view)
        assert_true(sidebar_contains(index_view, '<span class="has_small">1.0</span><small>1</small>'))
        index_view = self.app.get('/bugs/')
        assert_false(sidebar_contains(index_view, '<span class="has_small">1.0</span><small>1</small>'))
        assert_false(summary in index_view)

    def test_render_ticket(self):
        summary = 'test render ticket'
        ticket_view = self.new_ticket(summary=summary).follow()
        ticket_view.mustcontain(summary, 'Discussion')

    def test_render_index(self):
        index_view = self.app.get('/bugs/')
        assert 'No open tickets found.' in index_view
        assert 'Create Ticket' in index_view
        # No 'Create Ticket' button for user without 'write' perm
        r = self.app.get('/bugs/', extra_environ=dict(username='*anonymous'))
        assert 'Create Ticket' not in r

    def test_render_markdown_syntax(self):
        r = self.app.get('/bugs/markdown_syntax')
        assert_true('Markdown Syntax' in r)

    def test_ticket_diffs(self):
        self.new_ticket(summary='difftest', description='1\n2\n3\n')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'difftest',
            'description':'1\n3\n4\n',
        })
        r = self.app.get('/bugs/1/')
        assert '<span class="gd">-2</span>' in r, r.showbrowser()
        assert '<span class="gi">+4</span>' in r, r.showbrowser()

    def test_ticket_label_unlabel(self):
        summary = 'test labeling and unlabeling a ticket'
        self.new_ticket(summary=summary)
        self.app.post('/bugs/1/update_ticket',{
            'summary':'aaa',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'',
            'labels':u'yellow,greén'.encode('utf-8'),
            'labels_old':u'yellow,greén'.encode('utf-8'),
            'comment': ''
        })
        response = self.app.get('/bugs/1/')
        assert_true('yellow' in response)
        assert_true(u'greén' in response)
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
        assert file_name in ticket_editor, ticket_editor.showbrowser()
        req = self.app.get('/bugs/1/')
        file_link = req.html.findAll('form')[1].findAll('a')[-4]
        assert_equal(file_link.string, file_name)
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
        download = self.app.get(str(ticket_editor.html.findAll('form')[1].findAll('a')[-4]['href']))
        assert_equal(download.body, file_data)

    def test_new_image_attachment_content(self):
        h.set_context('test', 'bugs', neighborhood='Projects')
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(allura.__path__[0],'nf','allura','images',file_name)
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
        assert 'Related Pages' not in response

    def test_related_artifacts(self):
        summary = 'test sidebar logic for a ticket page'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'Related Pages' not in response
        self.app.post('/wiki/aaa/update', params={
                'title':'aaa',
                'text':'',
                'labels':'',
                'labels_old':'',
                'viewable_by-0.id':'all'})
        self.new_ticket(summary='bbb')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()

        h.set_context('test', 'wiki', neighborhood='Projects')
        a = wm.Page.query.find(dict(title='aaa')).first()
        a.text = '\n[bugs:#1]\n'
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        b = tm.Ticket.query.find(dict(ticket_num=2)).first()
        b.description = '\n[#1]\n'
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()

        response = self.app.get('/p/test/bugs/1/')
        assert 'Related' in response
        assert 'Wiki: aaa' in response
        assert 'Ticket: #2' in response

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
        assert 'nobody' in str(response.html.find('div', {'class': 'grid-5 ticket-assigned-to'}))

    def test_assign_ticket(self):
        summary = 'test assign ticket'
        self.new_ticket(summary=summary)
        response = self.app.get('/p/test/bugs/1/')
        assert 'nobody' in str(response.html.find('div', {'class': 'grid-5 ticket-assigned-to'}))
        response = self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'',
            'assigned_to':'test-admin',
            'labels':'',
            'labels_old':'',
            'comment': ''
        }).follow()
        assert 'test-admin' in str(response.html.find('div', {'class': 'grid-5 ticket-assigned-to'}))
        assert '<li><strong>summary</strong>: test assign ticket --&gt; zzz' in response
        assert '<li><strong>status</strong>: open --&gt; ccc' in response

    def test_custom_fields(self):
        params = dict(
            custom_fields=[
                dict(name='_priority', label='Priority', type='select',
                     options='normal urgent critical'),
                dict(name='_category', label='Category', type='string',
                     options=''),
                dict(name='_code_review', label='Code Review', type='user')],
            open_status_names='aa bb',
            closed_status_names='cc',
            )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))
        kw = {'custom_fields._priority':'normal',
              'custom_fields._category':'helloworld',
              'custom_fields._code_review':'test-admin'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        assert 'Priority:' in ticket_view
        assert 'normal' in ticket_view
        assert 'Test Admin' in ticket_view

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
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        assert '<strong>number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket',params={
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaa',
            'assigned_to':'',
            'labels':'',
            'labels_old':'',
            'custom_fields._number':'',
            'comment': ''
        }).follow()
        assert '<strong>number</strong>:  --&gt;' not in ticket_view
        ticket_view = self.app.post('/bugs/1/update_ticket',params={
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaa',
            'assigned_to':'',
            'labels':'',
            'labels_old':'',
            'custom_fields._number':'4',
            'comment': ''
        }).follow()
        assert '<strong>number</strong>:  --&gt;' in ticket_view

    def test_milestone_names(self):
        params = {
            'open_status_names': 'aa bb',
            'closed_status_names': 'cc',
            'custom_fields': [dict(
                    label='Milestone',
                    show_in_search='on',
                    type='milestone',
                    milestones=[
                        dict(name='aaaé'),
                        dict(name='bbb'),
                        dict(name='ccc')])] }
        self.app.post('/admin/bugs/set_custom_fields',
                      variable_encode(params),
                      status=302)
        self.new_ticket(summary='test milestone names')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'zzz',
            'description':'bbb',
            'status':'ccc',
            '_milestone':'aaaé',
            'assigned_to':'',
            'labels':'',
            'labels_old':'',
            'comment': ''
        })
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert 'aaaé' in ticket_view

    def test_milestone_rename(self):
        self.new_ticket(summary='test milestone rename')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'test milestone rename',
            'description':'',
            'status':'',
            '_milestone':'1.0',
            'assigned_to':'',
            'labels':'',
            'labels_old':'',
            'comment': ''
        })
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'Milestone' in ticket_view
        assert '1.0' in ticket_view
        assert 'zzzé' not in ticket_view
        r = self.app.post('/bugs/update_milestones',{
            'field_name':'_milestone',
            'milestones-0.old_name':'1.0',
            'milestones-0.new_name':'zzzé',
            'milestones-0.description':'',
            'milestones-0.complete':'Open',
            'milestones-0.due_date':''
        })
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert '1.0' not in ticket_view
        assert 'zzzé' in ticket_view

    def test_milestone_close(self):
        self.new_ticket(summary='test milestone close')
        r = self.app.get('/bugs/milestones')
        assert 'view closed' not in r
        r = self.app.post('/bugs/update_milestones',{
            'field_name':'_milestone',
            'milestones-0.old_name':'1.0',
            'milestones-0.new_name':'1.0',
            'milestones-0.description':'',
            'milestones-0.complete':'Closed',
            'milestones-0.due_date':''
        })
        r = self.app.get('/bugs/milestones')
        assert 'view closed' in r

    def test_subtickets(self):
        # create two tickets
        self.new_ticket(summary='test superticket')
        self.new_ticket(summary='test subticket')
        h.set_context('test', 'bugs', neighborhood='Projects')
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
        kw = {'custom_fields._days':'0'}
        self.new_ticket(summary='test superticket', **kw)
        self.new_ticket(summary='test subticket-1', **kw)
        self.new_ticket(summary='test subticket-2', **kw)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        h.set_context('test', 'bugs', neighborhood='Projects')
        super = tm.Ticket.query.get(ticket_num=1)
        sub1 = tm.Ticket.query.get(ticket_num=2)
        sub2 = tm.Ticket.query.get(ticket_num=3)

        # set values for the custom sum
        sub1.custom_fields['_days'] = '4.5'
        sub2.custom_fields['_days'] = '2.0'

        # make two tickets a subtickets of the other
        sub1.set_as_subticket_of(super._id)
        sub2.set_as_subticket_of(super._id)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

        # get a view on the first ticket, check for other ticket listed in sidebar
        ticket_view = self.app.get('/p/test/bugs/1/')
        assert 'days' in ticket_view
        assert '6.5' in ticket_view

    def test_edit_all_button(self):
        response = self.app.get('/p/test/bugs/search/')
        assert 'Edit All' not in response

    def test_new_ticket_validation(self):
        summary = 'ticket summary'
        response = self.app.get('/bugs/new/')
        assert not response.html.find('div', {'class':'error'})
        form = response.forms[1]
        form['ticket_form.labels'] = 'foo'
        # try submitting with no summary set and check for error message
        error_form = form.submit()
        assert error_form.forms[1]['ticket_form.labels'].value == 'foo'
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert (error_message.string == 'You must provide a Title' or \
                error_message.string == 'Missing value')
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.forms[1]['ticket_form.summary'] = summary
        success = error_form.forms[1].submit().follow().html
        assert success.findAll('form')[1].get('action') == '/p/test/bugs/1/update_ticket_from_widget'
        assert success.find('input', {'name':'ticket_form.summary'})['value'] == summary

    def test_edit_ticket_validation(self):
        old_summary = 'edit ticket test'
        new_summary = "new summary"
        self.new_ticket(summary=old_summary)
        response = self.app.get('/bugs/1/')
        # check that existing form is valid
        assert response.html.find('input', {'name':'ticket_form.summary'})['value'] == old_summary
        assert not response.html.find('div', {'class':'error'})
        form = response.forms[1]
        # try submitting with no summary set and check for error message
        form['ticket_form.summary'] = ""
        error_form = form.submit()
        error_message = error_form.html.find('div', {'class':'error'})
        assert error_message
        assert error_message.string == 'You must provide a Title'
        assert error_message.findPreviousSibling('input').get('name') == 'ticket_form.summary'
        # set a summary, submit, and check for success
        error_form.forms[1]['ticket_form.summary'] = new_summary
        r = error_form.forms[1].submit()
        assert r.status_int == 302, r.showbrowser()
        success = r.follow().html
        assert success.findAll('form')[1].get('action') == '/p/test/bugs/1/update_ticket_from_widget'
        assert success.find('input', {'name':'ticket_form.summary'})['value'] == new_summary

    def test_home(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        self.new_ticket(summary='test third ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/')
        assert 'test third ticket' in response

    def test_search(self):
        self.new_ticket(summary='test first ticket')
        self.new_ticket(summary='test second ticket')
        self.new_ticket(summary='test third ticket')
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        response = self.app.get('/p/test/bugs/search/?q=test')
        assert '3 results' in response, response.showbrowser()
        assert 'test third ticket' in response, response.showbrowser()

    def test_touch(self):
        self.new_ticket(summary='test touch')
        h.set_context('test', 'bugs', neighborhood='Projects')
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
            'summary': 'This is not too long.',
            'terms': 'aaa',
            'old_summary': '',
            'sort': ''}).follow()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'This is not too long.')
        r = self.app.post('/admin/bugs/bins/save_bin',{
            'summary': 'This will be truncated because it is too long to show in the sidebar without being ridiculous.',
            'terms': 'aaa',
            'old_summary': '',
            'sort': ''}).follow()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'This will be truncated because it is too long to show in the sidebar ...')

    def test_edit_saved_search(self):
        r = self.app.get('/admin/bugs/bins/')
        edit_form = r.form
        edit_form['bins-2.summary'] = 'Original'
        edit_form['bins-2.terms'] = 'aaa'
        edit_form.submit()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'Original')
        assert not sidebar_contains(r, 'New')
        r = self.app.get('/admin/bugs/bins/')
        edit_form = r.form
        edit_form['bins-2.summary'] = 'New'
        edit_form.submit()
        r = self.app.get('/bugs/')
        assert sidebar_contains(r, 'New')
        assert not sidebar_contains(r, 'Original')

    def test_discussion_paging(self):
        summary = 'test discussion paging'
        ticket_view = self.new_ticket(summary=summary).follow()
        for f in ticket_view.html.findAll('form'):
            if f.get('action', '').endswith('/post'):
                break
        post_content = 'ticket discussion post content'
        params = dict()
        inputs = f.findAll('input')
        for field in inputs:
            if field.has_key('name'):
                params[field['name']] = field.has_key('value') and field['value'] or ''
        params[f.find('textarea')['name']] = post_content
        r = self.app.post(f['action'].encode('utf-8'), params=params,
                          headers={'Referer': '/bugs/1/'.encode("utf-8")})
        r = self.app.get('/bugs/1/', dict(page=-1))
        assert_true(summary in r)
        r = self.app.get('/bugs/1/', dict(page=1))
        assert_true(post_content in r)
        # no pager if just one page
        assert_false('Page 1 of 1' in r)
        # add some more posts and check for pager
        for i in range(2):
            r = self.app.post(f['action'].encode('utf-8'), params=params,
                  headers={'Referer': '/bugs/1/'.encode("utf-8")})
        r = self.app.get('/bugs/1/', dict(page=1, limit=2))
        assert_true('Page 2 of 2' in r)

class TestMilestoneAdmin(TrackerTestController):
    def _post(self, params, **kw):
        params['open_status_names'] = 'aa bb'
        params['closed_status_names'] = 'cc'
        self.app.post('/admin/bugs/set_custom_fields',
                      params=variable_encode(params), **kw)
        return self.app.get('/admin/bugs/fields')

    def _post_milestones(self, milestones):
        params = {'custom_fields': [
            dict(label=mf['label'],
                 show_in_search='on',
                 type='milestone',
                 milestones=[
                    dict((k, v) for k, v in d.iteritems()) for d in mf['milestones']])
            for mf in milestones]}
        return self._post(params)

    def test_create_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        assert 'releases' in r
        assert '1.0-beta' in r

    def test_delete_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases':'1.0-beta'})
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 1
        r = self._post_milestones([])
        assert 'Releases' not in r
        assert '1.0-beta' not in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 0

    def test_rename_milestone_field(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases':'1.0-beta'})
        r = self._post_milestones([
            dict(label='versions', milestones=[dict(name='1.0/beta')])
        ])
        assert 'Releases' not in r
        assert 'versions' in r
        assert '1.0-beta' in r
        # TODO: This doesn't work - need to make milestone custom fields
        #       renameable.
        #assert tm.Ticket.query.find({
        #    'custom_fields._versions': '1.0-beta'}).count() == 1

    def test_create_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta'),
                                               dict(name='2.0')])
        ])
        assert '1.0-beta' in r
        assert '2.0' in r

    def test_delete_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0/beta')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases':'1.0-beta'})
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 1
        r = self._post_milestones([
            dict(label='releases', milestones=[])
        ])
        assert 'releases' in r
        assert '1.0-beta' not in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0-beta'}).count() == 0

    def test_rename_milestone(self):
        r = self._post_milestones([
            dict(label='releases', milestones=[dict(name='1.0')])
        ])
        self.new_ticket(summary='test new milestone',
                        **{'custom_fields._releases':'1.0'})
        r = self._post_milestones([
            dict(label='releases', milestones=[
                dict(name='1.1', old_name='1.0')])
        ])
        assert 'releases'in r
        assert '1.0' not in r
        assert '1.1' in r
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.0'}).count() == 0
        assert tm.Ticket.query.find({
            'custom_fields._releases': '1.1'}).count() == 1

def post_install_hook(app):
    role_anon = M.ProjectRole.by_name('*anonymous')._id
    app.config.acl.append(M.ACE.allow(role_anon, 'post'))
    app.config.acl.append(M.ACE.allow(role_anon, 'write'))

class TestEmailMonitoring(TrackerTestController):
    def __init__(self):
        super(TestEmailMonitoring, self).__init__()
        self.test_email = 'mailinglist@example.com'

    def _set_options(self, monitoring_type='AllTicketChanges'):
        r = self.app.post('/admin/bugs/set_options', params={
            'TicketMonitoringEmail': self.test_email,
            'TicketMonitoringType': monitoring_type,
            })
        return r

    def test_set_options(self):
        r = self._set_options()
        r = self.app.get('/admin/bugs/options')
        email = r.html.findAll(attrs=dict(name='TicketMonitoringEmail'))
        mtype = r.html.findAll('option', attrs=dict(value='AllTicketChanges'))
        assert email[0]['value'] == self.test_email
        assert mtype[0]['selected'] == 'selected'

    @td.with_tool('test', 'Tickets', 'doc-bugs', post_install_hook=post_install_hook)
    @patch('forgetracker.model.ticket.Notification.send_direct')
    def test_notifications_moderators(self, send_direct):
        self.new_ticket(summary='test moderation', mount_point='/doc-bugs/')
        self.app.post('/doc-bugs/1/update_ticket',{
            'summary':'test moderation',
            'comment':'test unmoderated post'
        }, extra_environ=dict(username='*anonymous'))
        send_direct.assert_called_with(str(M.User.query.get(username='test-admin')._id))

    @patch('forgetracker.model.ticket.Notification.send_simple')
    def test_notifications_new(self, send_simple):
        self._set_options('NewTicketsOnly')
        self.new_ticket(summary='test')
        self.app.post('/bugs/1/update_ticket',{
            'summary':'test',
            'description':'update',
        })
        send_simple.assert_called_once_with(self.test_email)

    @patch('forgetracker.tracker_main.M.Notification.send_simple')
    def test_notifications_all(self, send_simple):
        self._set_options()
        self.new_ticket(summary='test')
        send_simple.assert_called_once_with(self.test_email)
        send_simple.reset_mock()
        self.app.post('/bugs/1/update_ticket',{
            'summary':'test',
            'description':'update',
        })
        assert send_simple.call_count == 1, send_simple.call_count
        send_simple.assert_called_with(self.test_email)

class TestCustomUserField(TrackerTestController):
    def setUp(self):
        super(TestCustomUserField, self).setUp()
        params = dict(
            custom_fields=[
                dict(name='_code_review', label='Code Review', type='user',
                     show_in_search='on')],
            open_status_names='aa bb',
            closed_status_names='cc',
            )
        self.app.post(
            '/admin/bugs/set_custom_fields',
            params=variable_encode(params))

    def test_blank_user(self):
        kw = {'custom_fields._code_review': ''}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        # summary header shows 'nobody'
        assert ticket_view.html.findAll('label', 'simple',
            text='Code Review:')[1].parent.parent.text == 'Code Review:nobody'
        # form input is blank
        assert ticket_view.html.find('input',
            dict(name='ticket_form.custom_fields._code_review'))['value'] == ''

    def test_non_project_member(self):
        """ Test that you can't put a non-project-member user in a custom
        user field.
        """
        kw = {'custom_fields._code_review': 'test-user-0'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        # summary header shows 'nobody'
        assert ticket_view.html.findAll('label', 'simple',
            text='Code Review:')[1].parent.parent.text == 'Code Review:nobody'
        # form input is blank
        assert ticket_view.html.find('input',
            dict(name='ticket_form.custom_fields._code_review'))['value'] == ''

    def test_project_member(self):
        kw = {'custom_fields._code_review': 'test-admin'}
        ticket_view = self.new_ticket(summary='test custom fields', **kw).follow()
        # summary header shows 'nobody'
        assert ticket_view.html.findAll('label', 'simple',
            text='Code Review:')[1].parent.parent.text == 'Code Review:Test Admin'
        # form input is blank
        assert ticket_view.html.find('input',
            dict(name='ticket_form.custom_fields._code_review'))['value'] == 'test-admin'

    def test_change_user_field(self):
        kw = {'custom_fields._code_review': ''}
        r = self.new_ticket(summary='test custom fields', **kw).follow()
        f = r.forms[1]
        f['ticket_form.custom_fields._code_review'] = 'test-admin'
        r = f.submit().follow()
        assert '<li><strong>code_review</strong>: Test Admin' in r

    def test_search_results(self):
        kw = {'custom_fields._code_review': 'test-admin'}
        self.new_ticket(summary='test custom fields', **kw)
        r = self.app.get('/bugs/')
        assert r.html.find('table', 'ticket-list').findAll('th')[5].text == 'Code Review'
        assert r.html.find('table', 'ticket-list').tbody.tr.findAll('td')[5].text == 'Test Admin'

class TestHelpTextOptions(TrackerTestController):
    def _set_options(self, new_txt='', search_txt=''):
        r = self.app.post('/admin/bugs/set_options', params={
            'TicketHelpNew': new_txt,
            'TicketHelpSearch': search_txt,
            })
        return r

    def test_help_text(self):
        self._set_options(
                new_txt='**foo**',
                search_txt='*bar*')
        r = self.app.get('/bugs/')
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/search', params=dict(q='test'))
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/milestone/1.0/')
        assert '<em>bar</em>' in r
        r = self.app.get('/bugs/new/')
        assert '<strong>foo</strong>' in r

        self._set_options()
        r = self.app.get('/bugs/')
        assert len(r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/search', params=dict(q='test'))
        assert len(r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/milestone/1.0/')
        assert len(r.html.findAll(attrs=dict(id='search-ticket-help-msg'))) == 0
        r = self.app.get('/bugs/new/')
        assert len(r.html.findAll(attrs=dict(id='new-ticket-help-msg'))) == 0

def sidebar_contains(response, text):
    sidebar_menu = response.html.find('div', attrs={'id': 'sidebar'})
    return text in str(sidebar_menu)
