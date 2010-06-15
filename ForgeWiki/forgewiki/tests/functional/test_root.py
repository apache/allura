import os
import Image, StringIO
import pyforge

from nose.tools import assert_true

from forgewiki.tests import TestController
from forgewiki import model

# These are needed for faking reactor actions
import mock
from pyforge.lib import helpers as h
from pyforge.command import reactor
from pyforge.ext.search import search_main
from ming.orm.ormsession import ThreadLocalORMSession

#---------x---------x---------x---------x---------x---------x---------x
# RootController methods exposed:
#     index, new_page, search
# PageController methods exposed:
#     index, edit, history, diff, raw, revert, update
# CommentController methods exposed:
#     reply, delete

class TestRootController(TestController):
    def test_root_index(self):
        response = self.app.get('/wiki/TEST/')
        assert 'TEST' in response

    def test_root_markdown_syntax(self):
        response = self.app.get('/wiki/markdown_syntax/')
        assert 'Markdown Syntax' in response

    def test_root_wiki_help(self):
        response = self.app.get('/wiki/wiki_help/')
        assert 'Wiki Help' in response

    def test_root_browse_tags(self):
        response = self.app.get('/wiki/browse_tags/')
        assert 'Browse Tags' in response

    def test_root_browse_pages(self):
        response = self.app.get('/wiki/browse_pages/')
        assert 'Browse Pages' in response

    def test_root_new_page(self):
        response = self.app.get('/wiki/new_page?title=TEST')
        assert 'TEST' in response

    def test_root_new_search(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/search?q=TEST')
        assert 'Search wiki: TEST' in response

    def test_page_index(self):
        response = self.app.get('/wiki/TEST/')
        assert 'TEST' in response

    def test_page_edit(self):
        self.app.get('/wiki/TEST/index')
        response = self.app.post('/wiki/TEST/edit')
        assert 'TEST' in response

    def test_page_history(self):
        self.app.get('/wiki/TEST/')
        self.app.get('/wiki/TEST/update?title=TEST&text=text1&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all')
        self.app.get('/wiki/TEST/update?title=TEST&text=text2&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all')
        response = self.app.get('/wiki/TEST/history')
        assert 'TEST' in response
        # two revisions are shown
        assert '2 by Test Admin' in response
        assert '1 by Test Admin' in response
        # you can revert to an old revison, but not the current one
        assert response.html.find('a',{'href':'./revert?version=1'})
        assert not response.html.find('a',{'href':'./revert?version=2'})
        response = self.app.get('/wiki/TEST/history', extra_environ=dict(username='*anonymous'))
        # two revisions are shown
        assert '2 by Test Admin' in response
        assert '1 by Test Admin' in response
        # you cannot revert to any revision
        assert not response.html.find('a',{'href':'./revert?version=1'})
        assert not response.html.find('a',{'href':'./revert?version=2'})

    def test_page_diff(self):
        self.app.get('/wiki/TEST/')
        self.app.get('/wiki/TEST/revert?version=1')
        response = self.app.get('/wiki/TEST/')
        assert 'Unsubscribe' in response
        response = self.app.get('/wiki/TEST/diff?v1=0&v2=0')
        assert 'TEST' in response

    def test_page_raw(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/TEST/raw')
        assert 'TEST' in response

    def test_page_revert_no_text(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/TEST/revert?version=1')
        assert 'TEST' in response

    def test_page_revert_with_text(self):
        self.app.get('/wiki/TEST/')
        self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all')
        response = self.app.get('/wiki/TEST/revert?version=1')
        assert 'TEST' in response

    def test_page_update(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all')
        assert 'TEST' in response

    def test_page_tag_untag(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=red,blue&tags_old=red,blue&labels=&labels_old=&viewable_by-0.id=all')
        assert 'TEST' in response
        response = self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=red&tags_old=red&labels=&labels_old=&viewable_by-0.id=all')
        assert 'TEST' in response

    def test_page_label_unlabel(self):
        self.app.get('/wiki/TEST/')
        response = self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=&tags_old=&labels=yellow,green&labels_old=yellow,green&viewable_by-0.id=all')
        assert 'TEST' in response
        response = self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=&tags_old=&labels=yellow&labels_old=yellow&viewable_by-0.id=all')
        assert 'TEST' in response

    def test_new_attachment(self):
        self.app.get('/wiki/TEST/')
        content = file(__file__).read()
        response = self.app.post('/wiki/TEST/attach', upload_files=[('file_info', 'test_root.py', content)]).follow()
        assert 'test_root.py' in response

    def test_new_text_attachment_content(self):
        self.app.get('/wiki/TEST/')
        file_name = 'test_root.py'
        file_data = file(__file__).read()
        upload = ('file_info', file_name, file_data)
        page_editor = self.app.post('/wiki/TEST/attach', upload_files=[upload]).follow()
        download = page_editor.click(description=file_name)
        assert_true(download.body == file_data)

    def test_new_image_attachment_content(self):
        self.app.get('/wiki/TEST/')
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(pyforge.__path__[0],'public','nf','images',file_name)
        file_data = file(file_path).read()
        upload = ('file_info', file_name, file_data)
        self.app.post('/wiki/TEST/attach', upload_files=[upload])
        h.set_context('test', 'wiki')
        page = model.Page.query.find(dict(title='TEST')).first()
        filename = page.attachments.first().filename

        uploaded = Image.open(file_path)
        r = self.app.get('/wiki/TEST/attachment/'+filename)
        downloaded = Image.open(StringIO.StringIO(r.body))
        assert uploaded.size == downloaded.size
        r = self.app.get('/wiki/TEST/attachment/'+filename+'/thumb')

        thumbnail = Image.open(StringIO.StringIO(r.body))
        assert thumbnail.size == (255,255)

        # Make sure thumbnail is present
        r = self.app.get('/wiki/TEST/')
        img_srcs = [ i['src'] for i in r.html.findAll('img') ]
        assert ('/p/test/wiki/TEST/attachment/' + filename + '/thumb') in img_srcs, img_srcs
        # Update the page to embed the image, make sure the thumbnail is absent
        self.app.post('/wiki/TEST/update', params=dict(
                title='TEST',
                text='sometext\n[[img src=%s]]' % file_name))
        r = self.app.get('/wiki/TEST/')
        img_srcs = [ i['src'] for i in r.html.findAll('img') ]
        assert ('/p/test/wiki/TEST/attachment/' + filename) not in img_srcs, img_srcs
        assert ('./attachment/' + file_name) in img_srcs, img_srcs

    def test_sidebar_static_page(self):
        response = self.app.get('/wiki/TEST/')
        assert 'Edit this page' not in response
        assert 'Related Pages' not in response

    def test_sidebar_dynamic_page(self):
        response = self.app.get('/wiki/TEST/').follow()
        assert 'Edit TEST' in response
        assert 'Related Pages' not in response
        self.app.get('/wiki/aaa/')
        self.app.get('/wiki/bbb/')
        
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
        a = model.Page.query.find(dict(title='aaa')).first()
        a.text = '\n[TEST]\n'
        msg.data = dict(project_id=a.project_id,
                        mount_point=a.app_config.options.mount_point,
                        artifacts=[a.dump_ref()])
        add_artifacts(msg.data, msg)
        b = model.Page.query.find(dict(title='TEST')).first()
        b.text = '\n[bbb]\n'
        msg.data = dict(project_id=b.project_id,
                        mount_point=b.app_config.options.mount_point,
                        artifacts=[b.dump_ref()])
        add_artifacts(msg.data, msg)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        
        response = self.app.get('/wiki/TEST/')
        assert 'Related Pages' in response
        assert 'aaa' in response
        assert 'bbb' in response

    def test_page_permissions(self):
        response = self.app.get('/wiki/TEST/').follow()
        assert 'Viewable by' in response
        self.app.get('/wiki/TEST/update?title=TEST&text=sometext&tags=&tags_old=&labels=&labels_old=&viewable_by-0.id=all&viewable_by-0.delete=True')
        self.app.get('/wiki/TEST/', status=403)

    def test_show_discussion(self):
        self.app.get('/wiki/TEST/')
        wiki_page = self.app.get('/wiki/TEST/')
        assert wiki_page.html.find('div',{'id':'new_post_holder'})
        options_admin = self.app.get('/admin/wiki/options')
        assert options_admin.form['show_discussion'].checked
        options_admin.form['show_discussion'].checked = False
        options_admin2 = options_admin.form.submit().follow()
        assert not options_admin2.form['show_discussion'].checked
        wiki_page2 = self.app.get('/wiki/TEST/')
        assert not wiki_page2.html.find('div',{'id':'new_post_holder'})

    def test_show_left_bar(self):
        self.app.get('/wiki/TEST/')
        wiki_page = self.app.get('/wiki/TEST/')
        assert wiki_page.html.find('ul',{'class':'sidebarmenu'})
        options_admin = self.app.get('/admin/wiki/options')
        assert options_admin.form['show_left_bar'].checked
        options_admin.form['show_left_bar'].checked = False
        options_admin2 = options_admin.form.submit().follow()
        assert not options_admin2.form['show_left_bar'].checked
        wiki_page2 = self.app.get('/wiki/TEST/',extra_environ=dict(username='*anonymous'))
        assert not wiki_page2.html.find('ul',{'class':'sidebarmenu'})
        wiki_page3 = self.app.get('/wiki/TEST/')
        assert wiki_page3.html.find('ul',{'class':'sidebarmenu'})

    def test_show_right_bar(self):
        self.app.get('/wiki/TEST/')
        wiki_page = self.app.get('/wiki/TEST/')
        assert wiki_page.html.find('div',{'id':'sidebar-right'})
        options_admin = self.app.get('/admin/wiki/options')
        assert options_admin.form['show_right_bar'].checked
        options_admin.form['show_right_bar'].checked = False
        options_admin2 = options_admin.form.submit().follow()
        assert not options_admin2.form['show_right_bar'].checked
        wiki_page2 = self.app.get('/wiki/TEST/')
        assert not wiki_page2.html.find('div',{'id':'sidebar-right'})