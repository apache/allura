#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import os
from io import BytesIO
import allura
import json

import PIL
from ming.orm.ormsession import ThreadLocalORMSession
from mock import patch
from tg import config

from allura import model as M
from allura.lib import helpers as h
from allura.tests import decorators as td
from alluratest.controller import TestController

from forgewiki import model
from unittest.mock import MagicMock


class TestRootController(TestController):

    def setup_method(self, method):
        super().setup_method(method)
        self.setup_with_tools()

    @td.with_wiki
    def setup_with_tools(self):
        pass

    def _find_edit_form(self, resp):
        def cond(f):
            return f.id == 'page_edit_form'
        return self.find_form(resp, cond)

    def test_root_index(self):
        page_url = h.urlquote('/wiki/tést/')
        r = self.app.get(page_url).follow()
        assert 'tést' in r
        assert 'Create Page' in r
        # No 'Create Page' button if user doesn't have 'create' perm
        r = self.app.get('/wiki/Home',
                         extra_environ=dict(username='*anonymous'))
        assert 'Create Page' not in r, r

    def test_create_wiki_page(self):
        url = "/p/test/wiki/create_wiki_page/"
        r = self.app.get(url)
        assert 'test' in r
        assert 'Create page' in r.text

    def test_root_markdown_syntax(self):
        response = self.app.get('/wiki/markdown_syntax/', status=301)
        assert response.location.endswith('/nf/markdown_syntax')

    def test_root_browse_tags(self):
        response = self.app.get('/wiki/browse_tags/')
        assert 'Browse Labels' in response

    def test_root_browse_pages(self):
        response = self.app.get('/wiki/browse_pages/')
        assert 'Browse Pages' in response

    def test_root_new_page(self):
        response = self.app.get('/wiki/new_page?title=' + h.urlquote('tést'))
        assert response.location == 'http://localhost/wiki/t%C3%A9st/'

    def test_root_new_search(self):
        self.app.get(h.urlquote('/wiki/tést/'))
        response = self.app.get('/wiki/search/?q=' + h.urlquote('tést'))
        assert 'Search wiki: tést' in response

    def test_feed(self):
        for ext in ['', '.rss', '.atom']:
            self.app.get('/wiki/feed%s' % ext, status=200)

    @patch('allura.lib.helpers.ceil',  MagicMock(return_value=1))
    @patch('allura.lib.search.search')
    def test_search(self, search):
        r = self.app.get('/wiki/search/?q=test')
        assert (
            '<a href="/wiki/search/?q=test&amp;sort=score+asc" class="strong">relevance</a>' in r)
        assert (
            '<a href="/wiki/search/?q=test&amp;sort=mod_date_dt+desc" class="">date</a>' in r)

        p = M.Project.query.get(shortname='test')
        r = self.app.get('/wiki/search/?q=test&sort=score+asc')
        solr_query = {
            'short_timeout': True,
            'ignore_errors': False,
            'rows': 25,
            'start': 0,
            'qt': 'dismax',
            'qf': 'title^2 text',
            'pf': 'title^2 text',
            'fq': [
                'project_id_s:%s' % p._id,
                'mount_point_s:wiki',
                '-deleted_b:true',
                'type_s:("WikiPage" OR "WikiPage Snapshot")',
                'is_history_b:False',
            ],
            'hl': 'true',
            'hl.simple.pre': '#ALLURA-HIGHLIGHT-START#',
            'hl.simple.post': '#ALLURA-HIGHLIGHT-END#',
            'sort': 'score asc',
        }
        search.assert_called_with('test', **solr_query)

        r = self.app.get(
            '/wiki/search/?q=test&search_comments=on&history=on&sort=mod_date_dt+desc')
        solr_query['fq'][
            3] = 'type_s:("WikiPage" OR "WikiPage Snapshot" OR "Post")'
        solr_query['fq'].remove('is_history_b:False')
        solr_query['sort'] = 'mod_date_dt desc'
        search.assert_called_with('test', **solr_query)

        r = self.app.get('/wiki/search/?q=test&parser=standard')
        solr_query['sort'] = 'score desc'
        solr_query['fq'][3] = 'type_s:("WikiPage" OR "WikiPage Snapshot")'
        solr_query['fq'].append('is_history_b:False')
        solr_query.pop('qt')
        solr_query.pop('qf')
        solr_query.pop('pf')
        search.assert_called_with('test', **solr_query)

    def test_search_help(self):
        r = self.app.get('/wiki/search/?q=test')
        btn = r.html.find('a', attrs={'class': 'icon btn search_help_modal'})
        assert btn is not None, "Can't find a help button"
        div = r.html.find('div', attrs={'id': 'lightbox_search_help_modal'})
        assert div is not None, "Can't find help text"
        assert 'To search for an exact phrase' in div.text

    def test_nonexistent_page_edit(self):
        resp = self.app.get(h.urlquote('/wiki/tést/'))
        assert resp.location.endswith(h.urlquote('/wiki/tést/edit')), resp.location
        resp = resp.follow()
        assert 'tést' in resp

    def test_nonexistent_page_noedit(self):
        self.app.get(h.urlquote('/wiki/tést/'),
                     extra_environ=dict(username='*anonymous'),
                     status=404)
        self.app.get(h.urlquote('/wiki/tést/'),
                     extra_environ=dict(username='test-user'),
                     status=404)

    @patch('forgewiki.wiki_main.g.director.create_activity')
    def test_activity(self, create_activity):
        d = dict(title='foo', text='footext')
        self.app.post('/wiki/foo/update', params=d)
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'created'
        create_activity.reset_mock()
        d = dict(title='foo', text='new footext')
        self.app.post('/wiki/foo/update', params=d)
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'modified'
        create_activity.reset_mock()
        d = dict(title='new foo', text='footext')
        self.app.post('/wiki/foo/update', params=d)
        assert create_activity.call_count == 1
        assert create_activity.call_args[0][1] == 'renamed'

    def test_labels(self):
        response = self.app.post(
            '/wiki/foo-bar/update',
            params={
                'title': 'foo',
                'text': 'sometext',
                'labels': 'test label',
                }).follow()
        assert ('<a href="/p/test/wiki/search/?q=labels_t:%22test label%22&parser=standard">test label (1)</a>' in
                  response)

    def test_title_slashes(self):
        # forward slash not allowed in wiki page title - converted to dash
        response = self.app.post(
            '/wiki/foo-bar/update',
            params={
                'title': 'foo/bar',
                'text': 'sometext',
                'labels': '',
                }).follow()
        assert 'foo-bar' in response
        assert 'foo-bar' in response.request.url

    def test_dotted_page_name(self):
        r = self.app.post(
            '/wiki/page.dot/update',
            params={
                'title': 'page.dot',
                'text': 'text1',
                'labels': '',
                }).follow()
        assert 'page.dot' in r

    def test_subpage_attempt(self):
        self.app.get(h.urlquote('/wiki/tést/'))
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'text1',
                'labels': '',
                })
        assert '/p/test/wiki/Home/' in self.app.get(h.urlquote('/wiki/tést/Home/'))
        self.app.get(h.urlquote('/wiki/tést/notthere/'), status=404)

    def test_page_history(self):
        self.app.get(h.urlquote('/wiki/tést/'))
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'text1',
                'labels': '',
                })
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'text2',
                'labels': '',
                })
        response = self.app.get(h.urlquote('/wiki/tést/history'))
        assert 'tést' in response
        # two revisions are shown
        assert '<tr data-version="2" data-username="test-admin">' in response
        assert '<tr data-version="1" data-username="test-admin">' in response
        # you can revert to an old revison, but not the current one
        assert response.html.find('a', {'data-dialog-id': '1'}), response.html
        assert not response.html.find('a', {'data-dialog-id': '2'})
        response = self.app.get(h.urlquote('/wiki/tést/history'),
                                extra_environ=dict(username='*anonymous'))
        # two revisions are shown
        assert '<tr data-version="2" data-username="test-admin">' in response
        assert '<tr data-version="1" data-username="test-admin">' in response
        # you cannot revert to any revision
        assert not response.html.find('a', {'data-dialog-id': '1'})
        assert not response.html.find('a', {'data-dialog-id': '2'})

        # view an older version
        response = self.app.get(h.urlquote('/wiki/tést/') + '?version=1')
        response.mustcontain('text1')
        response.mustcontain(no='text2')

    def test_page_diff(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        self.app.post(h.urlquote('/wiki/tést/revert'), params=dict(version='1'))
        response = self.app.get(h.urlquote('/wiki/tést/diff') + '?v1=0&v2=0')
        assert 'tést' in response
        d = dict(title='testdiff', text="""**Optionally**, you may also want to remove all the unused accounts that have accumulated (one was created for *every* logged in SF-user who has visited your MediaWiki hosted app):

                                            ~~~~~
                                            php removeUnusedAccounts.php --delete
                                            ~~~~~

                                            #### 6) Import image (and other) files into your Mediawiki install ####

                                            Upload the backup of your data files to the project web.

                                            ~~~~~
                                            scp projectname_mediawiki_files.tar.gz USERNAME@web.domain.net:
                                            ~~~~~

                                            In the project web shell, unpack the files to the images directory of you wiki installation. In the backup, the images are in a subfolder *projectname*, so follow these steps:

                                            ~~~~~
                                            cd wiki
                                            mkdir oldimages
                                            cd oldimages
                                            tar -xvzf ../../../projectname_mediawiki_files.tar.gz
                                            mv projectname/* ../images/
                                            cd ..
                                            rm -r oldimages
                                            # Now fix permissons. Wrong permissions may cause massive slowdown!
                                            chown yournick:apache images/ --recursive
                                            chmod 775 images/ --recursive
                                            ~~~~~

                                            **TODO: FIXME:** The following can't be quite correct:

                                            Now hit your wiki a few times from a browser. Initially, it will be dead slow, as it is trying to build thumbnails for the images. And it will time out, a lot. Keep hitting reload, until it works.

                                            **Note:** The logo shown in the sidebar is no longer stored as an object in the wiki (as it was in the Hosted App installation). Rather save it as a regular file, then edit LocalSettings.php, adding""")
        self.app.post('/wiki/testdiff/update', params=d)
        d = dict(title='testdiff', text="""**Optionally**, you may also want to remove all the unused accounts that have accumulated (one was created for *every* logged in SF-user who has visited your MediaWiki hosted app):

                                            ~~~~~
                                            php removeUnusedAccounts.php --delete
                                            ~~~~~

                                            #### 6) Import image (and other) files into your Mediawiki install ####

                                            Upload the backup of your data files to the project web.

                                            ~~~~~
                                            scp projectname_mediawiki_files.tar.gz USERNAME@web.domain.net:
                                            ~~~~~

                                            In the project web shell, unpack the files to the images directory of you wiki installation. In the backup, the images are in a subfolder *projectname*, so follow these steps:

                                            ~~~~~
                                            cd wiki
                                            mkdir oldimages
                                            cd oldimages
                                            tar -xvzf ../../../projectname_mediawiki_files.tar.gz
                                            mv projectname/* ../images/
                                            cd ..
                                            rm -r oldimages
                                            # Now fix permissions. Wrong permissions may cause a massive slowdown!
                                            chown yournick:apache images/ --recursive
                                            chmod 775 images/ --recursive
                                            ~~~~~

                                            **TODO: FIXME:** The following can't be quite correct:

                                            Now hit your wiki a few times from a browser. Initially, it will be dead slow, as it is trying to build thumbnails for the images. And it will time out, a lot. Keep hitting reload, until it works.

                                            **Note:** The logo shown in the sidebar is no longer stored as an object in the wiki (as it was in the Hosted App installation). Rather save it as a regular file, then edit LocalSettings.php, adding

                                            <script>alert(1)</script>""")
        self.app.post('/wiki/testdiff/update', params=d)
        response = self.app.get('/wiki/testdiff/diff?v1=1&v2=2')
        assert ('# Now fix <del> permissons. </del> <ins> permissions. </ins> '
                  'Wrong permissions may cause <ins> a </ins> massive slowdown!' in
                  response)
        assert '<script>alert' not in response
        assert '&lt;script&gt;alert' in response
        response = self.app.get('/wiki/testdiff/diff?v1=2&v2=1')
        assert ('# Now fix <del> permissions. </del> <ins> permissons. </ins> '
                  'Wrong permissions may cause <del> a </del> massive slowdown!' in
                  response)

    def test_page_raw(self):
        self.app.post(
            '/wiki/TEST/update',
            params={
                'title': 'TEST',
                'text': 'sometext',
                'labels': '',
                })
        response = self.app.get('/wiki/TEST/raw')
        assert 'TEST' in response

    def test_page_revert_no_text(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': '',
                'labels': '',
                })
        response = self.app.post(h.urlquote('/wiki/tést/revert'), params=dict(version='1'))
        assert '.' in response.json['location']
        response = self.app.get(h.urlquote('/wiki/tést/'))
        assert 'tést' in response

    def test_page_revert_with_text(self):
        self.app.get(h.urlquote('/wiki/tést/'))
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        response = self.app.post(h.urlquote('/wiki/tést/revert'), params=dict(version='1'))
        assert '.' in response.json['location']
        response = self.app.get(h.urlquote('/wiki/tést/'))
        assert 'tést' in response

    @patch('forgewiki.wiki_main.g.spam_checker')
    def test_page_update(self, spam_checker):
        self.app.get(h.urlquote('/wiki/tést/'))
        response = self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        assert spam_checker.check.call_args[0][0] == 'tést\nsometext'
        assert response.location == 'http://localhost/wiki/t%C3%A9st/'

    def test_page_get_markdown(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': '- [ ] checkbox',
                'labels': '',
                })
        response = self.app.get(h.urlquote('/wiki/tést/get_markdown'))
        assert '- [ ] checkbox' in response

    def test_page_update_markdown(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': '- [ ] checkbox',
                'labels': '',
                })
        response = self.app.post(
            h.urlquote('/wiki/tést/update_markdown'),
            params={
                'text': '- [x] checkbox'})
        print(response)
        assert response.json['status'] == 'success'
        # anon users can't edit markdown
        response = self.app.post(
            h.urlquote('/wiki/tést/update_markdown'),
            params={
                'text': '- [x] checkbox'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['status'] == 'no_permission'

    def test_page_label_unlabel(self):
        self.app.get(h.urlquote('/wiki/tést/'))
        response = self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': 'yellow,green',
                })
        assert response.location == 'http://localhost/wiki/t%C3%A9st/'
        response = self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': 'yellow',
                })
        assert response.location == 'http://localhost/wiki/t%C3%A9st/'

    def test_page_label_count(self):
        labels = "label"
        for i in range(1, 100):
            labels += ',label%s' % i
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': labels,
                })
        r = self.app.get('/wiki/browse_tags/')
        assert 'results of 100 ' in r
        assert '<div class="page_list">' in r
        assert '(Page 1 of 4)' in r
        assert '<td>label30</td>' in r
        assert '<td>label1</td>' in r

        r = self.app.get('/wiki/browse_tags/?page=2')
        # back to first page (page 0) doesn't need page=0 in url:
        assert '<a href="/wiki/browse_tags/">' in r
        assert '<a href="/wiki/browse_tags/?page=0">' not in r
        assert '<td>label69</td>' in r
        assert '<td>label70</td>' in r
        r.mustcontain('canonical')
        canonical = r.html.select_one('link[rel=canonical]')
        assert 'browse_tags' in canonical['href']
        next = r.html.select_one('link[rel=next]')
        assert 'page=3' in next['href']
        prev = r.html.select_one('link[rel=prev]')
        assert 'page=1' in prev['href']

        r = self.app.get('/wiki/browse_tags/?page=0')
        canonical = r.html.select_one('link[rel=canonical]')
        assert 'page=' not in canonical

    def test_new_attachment(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        content = open(__file__, 'rb').read()
        self.app.post(h.urlquote('/wiki/tést/attach'),
                      upload_files=[('file_info', 'test_root.py', content)])
        response = self.app.get(h.urlquote('/wiki/tést/'))
        assert 'test_root.py' in response

    def test_attach_two_files(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        content = open(__file__, 'rb').read()
        self.app.post(h.urlquote('/wiki/tést/attach'),
                      upload_files=[('file_info', 'test1.py', content), ('file_info', 'test2.py', content)])
        response = self.app.get(h.urlquote('/wiki/tést/'))
        assert 'test1.py' in response
        assert 'test2.py' in response

    def test_new_text_attachment_content(self):
        self.app.post(
            h.urlquote('/wiki/tést/update'),
            params={
                'title': 'tést'.encode(),
                'text': 'sometext',
                'labels': '',
                })
        file_name = 'test_root.py'
        file_data = open(__file__, 'rb').read()
        upload = ('file_info', file_name, file_data)
        self.app.post(h.urlquote('/wiki/tést/attach'), upload_files=[upload])
        page_editor = self.app.get(h.urlquote('/wiki/tést/edit'))
        download = page_editor.click(description=file_name)
        assert download.body == file_data

    def test_new_image_attachment_content(self):
        self.app.post('/wiki/TEST/update', params={
            'title': 'TEST',
            'text': 'sometext',
            'labels': '',
            })
        file_name = 'neo-icon-set-454545-256x350.png'
        file_path = os.path.join(
            allura.__path__[0], 'nf', 'allura', 'images', file_name)
        file_data = open(file_path, 'rb').read()
        upload = ('file_info', file_name, file_data)
        self.app.post('/wiki/TEST/attach', upload_files=[upload])
        h.set_context('test', 'wiki', neighborhood='Projects')
        page = model.Page.query.find(dict(title='TEST')).first()
        filename = page.attachments[0].filename

        uploaded = PIL.Image.open(file_path)
        r = self.app.get('/wiki/TEST/attachment/' + filename)
        downloaded = PIL.Image.open(BytesIO(r.body))
        assert uploaded.size == downloaded.size
        r = self.app.get('/wiki/TEST/attachment/' + filename + '/thumb')

        thumbnail = PIL.Image.open(BytesIO(r.body))
        assert thumbnail.size == (100, 100)

        # Make sure thumbnail is absent
        r = self.app.get('/wiki/TEST/')
        img_srcs = [i['src'] for i in r.html.findAll('img')]
        assert ('/p/test/wiki/TEST/attachment/' +
                filename) not in img_srcs, img_srcs

    def test_sidebar_static_page(self):
        response = self.app.get(h.urlquote('/wiki/tést/'))
        assert 'Edit this page' not in response
        assert 'Related Pages' not in response

    def test_related_links(self):
        response = self.app.get('/wiki/TEST/').follow()
        assert 'Edit TEST' in response
        assert 'Related' not in response
        self.app.post('/wiki/TEST/update', params={
            'title': 'TEST',
            'text': 'sometext',
            'labels': '',
            })
        self.app.post('/wiki/aaa/update', params={
            'title': 'aaa',
            'text': '',
            'labels': '',
            })
        self.app.post('/wiki/bbb/update', params={
            'title': 'bbb',
            'text': '',
            'labels': '',
            })

        h.set_context('test', 'wiki', neighborhood='Projects')
        a = model.Page.query.find(dict(title='aaa')).first()
        a.text = '\n[TEST]\n'
        b = model.Page.query.find(dict(title='TEST')).first()
        b.text = '\n[bbb]\n'
        ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

        response = self.app.get('/wiki/TEST/')
        assert 'Related' in response
        assert 'aaa' in response
        assert 'bbb' in response

    def test_show_discussion(self):
        self.app.post(h.urlquote('/wiki/tést/update'), params={
            'title': 'tést'.encode(),
            'text': 'sometext',
            'labels': '',
            })
        wiki_page = self.app.get(h.urlquote('/wiki/tést/'))
        assert wiki_page.html.find('div', {'id': 'new_post_holder'})
        options_admin = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert options_admin.form['show_discussion'].checked
        options_admin.form['show_discussion'].checked = False
        options_admin.form.submit()
        options_admin2 = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert not options_admin2.form['show_discussion'].checked
        wiki_page2 = self.app.get(h.urlquote('/wiki/tést/'))
        assert not wiki_page2.html.find('div', {'id': 'new_post_holder'})

    def test_show_left_bar(self):
        self.app.post(h.urlquote('/wiki/tést/update'), params={
            'title': 'tést'.encode(),
            'text': 'sometext',
            'labels': '',
            })
        wiki_page = self.app.get(h.urlquote('/wiki/tést/'))
        assert wiki_page.html.find('ul', {'class': 'sidebarmenu'})
        options_admin = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert options_admin.form['show_left_bar'].checked
        options_admin.form['show_left_bar'].checked = False
        options_admin.form.submit()
        options_admin2 = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert not options_admin2.form['show_left_bar'].checked
        wiki_page2 = self.app.get(
            h.urlquote('/wiki/tést/'), extra_environ=dict(username='*anonymous'))
        assert not wiki_page2.html.find('ul', {'class': 'sidebarmenu'})
        wiki_page3 = self.app.get(h.urlquote('/wiki/tést/'))
        assert not wiki_page3.html.find('ul', {'class': 'sidebarmenu'})

    def test_show_metadata(self):
        self.app.post(h.urlquote('/wiki/tést/update'), params={
            'title': 'tést'.encode(),
            'text': 'sometext',
            'labels': '',
            })
        wiki_page = self.app.get(h.urlquote('/wiki/tést/'))
        assert wiki_page.html.find('div', {'class': 'editbox'})
        options_admin = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert options_admin.form['show_right_bar'].checked
        options_admin.form['show_right_bar'].checked = False
        options_admin.form.submit()
        options_admin2 = self.app.get(
            '/admin/wiki/options', validate_chunk=True)
        assert not options_admin2.form['show_right_bar'].checked
        wiki_page2 = self.app.get(h.urlquote('/wiki/tést/'))
        assert not wiki_page2.html.find('div', {'class': 'editbox'})

    def test_change_home_page(self):
        self.app.post(h.urlquote('/wiki/tést/update'), params={
            'title': 'our_néw_home'.encode(),
            'text': 'sometext',
            'labels': '',
            })
        homepage_admin = self.app.get('/admin/wiki/home', validate_chunk=True)
        assert homepage_admin.form['new_home'].value == 'Home'
        homepage_admin.form['new_home'].value = 'our_néw_home'
        homepage_admin.form.submit()
        root_path = self.app.get('/wiki/', status=301)
        assert root_path.location.endswith('/wiki/our_n%C3%A9w_home/'), root_path.location

    def test_edit_mount_label(self):
        r = self.app.get('/admin/wiki/edit_label', validate_chunk=True)
        assert r.form['mount_label'].value == 'Wiki'
        r = self.app.post('/admin/wiki/update_label', params=dict(
            mount_label='Tricky Wiki'))
        assert M.MonQTask.query.find({
            'task_name': 'allura.tasks.event_tasks.event',
            'args': 'project_menu_updated'
        }).all()
        r = self.app.get('/admin/wiki/edit_label', validate_chunk=True)
        assert r.form['mount_label'].value == 'Tricky Wiki'

    def test_page_links_are_colored(self):
        self.app.get('/wiki/space%20page/')
        params = {
            'title': 'space page',
            'text': '''There is a space in the title!''',
            'labels': '',
            }
        self.app.post('/wiki/space%20page/update', params=params)
        self.app.get('/wiki/TEST/')
        params = {
            'title': 'TEST',
            'text': '''
* Here is a link to [this page](TEST)
* Here is a link to [another page](Some page which does not exist)
* Here is a link to [space page space](space page)
* Here is a link to [space page escape](space%20page)
* Here is a link to [TEST]
* Here is a link to [Some page which does not exist]
* Here is a link to [space page]
* Here is a link to [space%20page]
* Here is a link to [another attach](TEST/attachment/attach.txt)
* Here is a link to [attach](TEST/attachment/test_root.py)
''',
            'labels': '',
            }
        self.app.post('/wiki/TEST/update', params=params)
        content = open(__file__, 'rb').read()
        self.app.post('/wiki/TEST/attach',
                      upload_files=[('file_info', 'test_root.py', content)])
        r = self.app.get('/wiki/TEST/')
        found_links = 0
        for link in r.html.findAll('a'):
            if link.contents == ['this page']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['another page']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['space page space']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['space page escape']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['[TEST]']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['[Some page which does not exist]']:
                assert 'notfound' in link.get('class', [])
                found_links += 1
            if link.contents == ['[space page]']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['[space%20page]']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
            if link.contents == ['another attach']:
                assert 'notfound' in link.get('class', [])
                found_links += 1
            if link.contents == ['attach']:
                assert 'notfound' not in link.get('class', [])
                found_links += 1
        assert found_links == 10, 'Wrong number of links found'

    def test_home_rename(self):
        assert 'The resource has been moved to http://localhost/p/test/wiki/Home/;' in self.app.get(
            '/p/test/wiki/')
        req = self.app.get('/p/test/wiki/Home/edit')
        form = self._find_edit_form(req)
        form['title'].value = 'new_title'
        form.submit()
        assert 'The resource has been moved to http://localhost/p/test/wiki/new_title/;' in self.app.get(
            '/p/test/wiki/')

    @patch.dict('allura.lib.app_globals.config', markdown_cache_threshold='0')
    def test_cached_html(self):
        """Ensure cached html is not escaped."""
        html = '<p><span>My Html</span></p>'
        self.app.post('/wiki/cache/update', params={
            'title': 'cache',
            'text': html,
            'labels': '',
            })
        # first request caches html, second serves from cache
        r = self.app.get('/wiki/cache/')
        r = self.app.get('/wiki/cache/')
        assert html in r

    def test_page_delete(self):
        self.app.post('/wiki/aaa/update', params={
            'title': 'aaa',
            'text': '111',
            'labels': '',
            })
        self.app.post('/wiki/bbb/update', params={
            'title': 'bbb',
            'text': '222',
            'labels': '',
            })
        response = self.app.get('/wiki/browse_pages/')
        assert 'aaa' in response
        assert 'bbb' in response
        self.app.post('/wiki/bbb/delete')
        response = self.app.get('/wiki/browse_pages/')
        assert 'aaa' in response
        assert '?deleted=True">bbb' in response
        n = M.Notification.query.get(subject="[test:wiki] test-admin removed page bbb")
        assert '222' in n.text

        # view deleted page
        response = response.click('bbb')
        assert '(deleted)' in response
        deletedpath = response.request.path_info

        # undelete it
        undelete_url = deletedpath + 'undelete'
        response = self.app.post(undelete_url)
        assert response.json == {'location': './edit'}
        response = self.app.get(deletedpath + 'edit')
        assert 'Edit bbb' in response

    def test_mailto_links(self):
        self.app.get('/wiki/test_mailto/')
        params = {
            'title': 'test_mailto',
            'text': '''
* Automatic mailto #1 <darth.vader@deathstar.org>
* Automatic mailto #2 <mailto:luke.skywalker@tatooine.org>
* Handmaid mailto <a href="mailto:yoda@jedi.org">Email Yoda</a>
''',
            'labels': '',
            }
        self.app.post('/wiki/test_mailto/update', params=params)
        r = self.app.get('/wiki/test_mailto/')
        mailto_links = 0
        for link in r.html.findAll('a'):
            if link.get('href') == 'mailto:darth.vader@deathstar.org':
                assert 'notfound' not in link.get('class', '')
                mailto_links += 1
            if link.get('href') == 'mailto:luke.skywalker@tatooine.org':
                assert 'notfound' not in link.get('class', '')
                mailto_links += 1
            if link.get('href') == 'mailto:yoda@jedi.org':
                assert link.contents == ['Email Yoda']
                assert 'notfound' not in link.get('class', '')
                mailto_links += 1
        assert mailto_links == 3, 'Wrong number of mailto links'

    def test_user_browse_page(self):
        r = self.app.get('/wiki/browse_pages/')
        assert '<td><a href="/u/test-admin/profile/" class="user-mention">test-admin</a></td>' in r

    def test_subscribe(self):
        user = M.User.query.get(username='test-user')
        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get('/p/test/wiki/Home/', extra_environ={'username': str(user.username)})
        sidebar_menu = r.html.find('div', attrs={'id': 'sidebar'})
        assert 'Subscribe to wiki' in str(sidebar_menu)
        # subscribe
        self.app.post('/p/test/wiki/subscribe', {'subscribe': 'True'},
                      extra_environ={'username': str(user.username)}).follow()
        # user is subscribed
        assert M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get('/p/test/wiki/Home/', extra_environ={'username': str(user.username)})
        sidebar_menu = r.html.find('div', attrs={'id': 'sidebar'})
        assert 'Unsubscribe' in str(sidebar_menu)
        # unsubscribe
        self.app.post('/p/test/wiki/subscribe', {'unsubscribe': 'True'},
                      extra_environ={'username': str(user.username)}).follow()
        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get('/p/test/wiki/Home/', extra_environ={'username': str(user.username)})
        sidebar_menu = r.html.find('div', attrs={'id': 'sidebar'})
        assert 'Subscribe to wiki' in str(sidebar_menu)

    def test_rate_limit_new_page(self):
        # Set rate limit to unlimit
        with h.push_config(config, **{'forgewiki.rate_limits': '{}'}):
            r = self.app.get('/p/test/wiki/new-page-title/')
            assert r.status_int == 302
            assert (
                r.location ==
                'http://localhost/p/test/wiki/new-page-title/edit')
            assert self.webflash(r) == ''
        # Set rate limit to 1 in first hour of project
        with h.push_config(config, **{'forgewiki.rate_limits': '{"3600": 1}'}):
            r = self.app.get('/p/test/wiki/new-page-title/')
            assert r.status_int == 302
            assert r.location == 'http://localhost/p/test/wiki/'
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert (
                wf['message'] ==
                'Page create/edit rate limit exceeded. Please try again later.')

    def test_rate_limit_update(self):
        # Set rate limit to unlimit
        with h.push_config(config, **{'forgewiki.rate_limits': '{}'}):
            r = self.app.post(
                '/p/test/wiki/page1/update',
                dict(text='Some text', title='page1')).follow()
            assert 'Some text' in r
            p = model.Page.query.get(title='page1')
            assert p is not None
        # Set rate limit to 1 in first hour of project
        with h.push_config(config, **{'forgewiki.rate_limits': '{"3600": 1}'}):
            r = self.app.post(
                '/p/test/wiki/page2/update',
                dict(text='Some text', title='page2'))
            assert r.status_int == 302
            assert r.location == 'http://localhost/p/test/wiki/'
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert (
                wf['message'] ==
                'Page create/edit rate limit exceeded. Please try again later.')
            p = model.Page.query.get(title='page2')
            assert p is None

    def test_rate_limit_by_user(self):
        # also test that multiple edits to a page counts as one page towards the limit

        # test/wiki/Home and test/sub1/wiki already were created by this user
        # and proactively get the user-project wiki created (otherwise it'll be created during the subsequent edits)
        self.app.get('/u/test-admin/wiki/')
        with h.push_config(config, **{'forgewiki.rate_limits_per_user': '{"3600": 5}'}):
            r = self.app.post('/p/test/wiki/page123/update',  # page 4 (remember, 3 other projects' wiki pages)
                              dict(text='Starting a new page, ok', title='page123'))
            assert self.webflash(r) == ''
            r = self.app.post('/p/test/wiki/page123/update',
                              dict(text='Editing some', title='page123'))
            assert self.webflash(r) == ''
            r = self.app.post('/p/test/wiki/page123/update',
                              dict(text='Still editing', title='page123'))
            assert self.webflash(r) == ''
            r = self.app.post('/p/test/wiki/pageABC/update',  # page 5
                              dict(text='Another new page', title='pageABC'))
            assert self.webflash(r) == ''
            r = self.app.post('/p/test/wiki/pageZZZZZ/update',  # page 6
                              dict(text='This new page hits the limit', title='pageZZZZZ'))
            wf = json.loads(self.webflash(r))
            assert wf['status'] == 'error'
            assert wf['message'] == 'Page create/edit rate limit exceeded. Please try again later.'

    def test_sidebar_admin_menu(self):
        r = self.app.get('/p/test/wiki/Home/')
        menu = r.html.find('div', {'id': 'sidebar-admin-menu'})
        assert menu['class'] == ['hidden']  # (not expanded)
        menu = [li.find('span').getText() for li in menu.findAll('li')]
        assert (
            menu ==
            ['Set Home', 'Permissions', 'Options', 'Rename', 'Delete Everything'])

    def test_sidebar_admin_menu_is_expanded(self):
        r = self.app.get('/p/test/admin/wiki/permissions')
        menu = r.html.find('div', {'id': 'sidebar-admin-menu'})
        assert 'hidden' not in menu.get('class', [])  # expanded

    def test_sidebar_admin_menu_invisible_to_not_admin(self):
        def assert_invisible_for(username):
            env = {'username': str(username)}
            r = self.app.get('/p/test/wiki/Home/', extra_environ=env)
            menu = r.html.find('div', {'id': 'sidebar-admin-menu'})
            assert menu is None
        assert_invisible_for('*anonymous')
        assert_invisible_for('test-user')

    def test_no_index_tag_on_empty_wiki(self):
        r = self.app.get('/u/test-user/wiki/Home/')
        assert 'content="noindex, follow"' in r.text
