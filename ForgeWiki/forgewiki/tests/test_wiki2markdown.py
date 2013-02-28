import mock
import json
from datetime import datetime
from IPython.testing.decorators import module_not_available, skipif

from forgewiki.scripts.wiki2markdown.extractors import MySQLExtractor
from forgewiki.scripts.wiki2markdown.loaders import MediawikiLoader
from alluratest.controller import setup_basic_test
from allura import model as M
from forgewiki import model as WM
from allura.lib import helpers as h

from pylons import tmpl_context as context


class TestMySQLExtractor(object):

    def setUp(self):
        setup_basic_test()
        self.options = mock.Mock()
        self.options.dump_dir = '/tmp/w2m_test'

        # monkey-patch MySQLExtractor for test
        def pages(self):
            yield {'page_id': 1, 'title': 'Test title'}
            yield {'page_id': 2, 'title': 'Main_Page'}
            yield {'page_id': 3, 'title': 'Test'}

        def history(self, page_id):
            data = {
                1: [
                    {'timestamp': 1, 'text': "Test", 'username': 'test-user'},
                    {'timestamp': 2, 'text': "Test Text", 'username': 'bad'}
                ],
                2: [
                    {'timestamp': 1, 'text': "Main_Page", 'username': 'b'},
                    {'timestamp': 2, 'text': "Main_Page text", 'username': 'b'}
                ],
                3: [
                    {'timestamp': 1, 'text': "Some test text", 'username': ''},
                    {'timestamp': 2, 'text': "", 'username': ''}
                ]
            }
            revisions = data[page_id]
            for rev in revisions:
                yield rev

        def talk(self, page_title):
            return {
                'text': 'Talk for page %s.' % page_title,
                'timestamp': 1,
                'username': 'test-user'
            }

        def attachments(self, *args, **kwargs):
            # make 'empty' iterator
            if False:
                yield

        MySQLExtractor._pages = pages
        MySQLExtractor._history = history
        MySQLExtractor._talk = talk
        MySQLExtractor._attachments = attachments
        self.extractor = MySQLExtractor(self.options)

    def test_extract_pages(self):
        """Test that pages and edit history extracted properly"""
        self.extractor.extract_pages()

        # rev 1 of page 1
        with open('/tmp/w2m_test/pages/1/history/1.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 1,
            'text': 'Test',
            'page_id': 1,
            'title': 'Test title',
            'username': 'test-user'
        }
        assert page == res_page

        # rev 2 of page 1
        with open('/tmp/w2m_test/pages/1/history/2.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 2,
            'text': 'Test Text',
            'page_id': 1,
            'title': 'Test title',
            'username': 'bad'
        }
        assert page == res_page

        # rev 1 of page 2
        with open('/tmp/w2m_test/pages/2/history/1.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 1,
            'text': 'Main_Page',
            'page_id': 2,
            'title': 'Main_Page',
            'username': 'b'
        }
        assert page == res_page

        # rev 2 of page 2
        with open('/tmp/w2m_test/pages/2/history/2.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 2,
            'text': 'Main_Page text',
            'page_id': 2,
            'title': 'Main_Page',
            'username': 'b'
        }
        assert page == res_page

        # rev 1 of page 3
        with open('/tmp/w2m_test/pages/3/history/1.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 1,
            'text': 'Some test text',
            'page_id': 3,
            'title': 'Test',
            'username': ''
        }
        assert page == res_page

        # rev 2 of page 3
        with open('/tmp/w2m_test/pages/3/history/2.json', 'r') as f:
            page = json.load(f)
        res_page = {
            'timestamp': 2,
            'text': '',
            'page_id': 3,
            'title': 'Test',
            'username': ''
        }
        assert page == res_page

    def test_extract_talk(self):
        """Test that talk pages extracted properly."""
        pages = [
            {'page_id': 1, 'title': 'Test 1'},
            {'page_id': 2, 'title': 'Test 2'},
            {'page_id': 3, 'title': 'Test 3'},
        ]
        for page in pages:
            self.extractor.extract_talk(page)

        with open('/tmp/w2m_test/pages/1/discussion.json', 'r') as f:
            page = json.load(f)
        assert page == {
                        'text': 'Talk for page Test 1.',
                        'username': 'test-user',
                        'timestamp': 1}

        with open('/tmp/w2m_test/pages/2/discussion.json', 'r') as f:
            page = json.load(f)
        assert page == {
                        'text': 'Talk for page Test 2.',
                        'timestamp': 1,
                        'username': 'test-user'}

        with open('/tmp/w2m_test/pages/3/discussion.json', 'r') as f:
            page = json.load(f)
        assert page == {
                        'text': 'Talk for page Test 3.',
                        'timestamp': 1,
                        'username': 'test-user'}


class TestMediawikiLoader(object):

    def setUp(self):
        setup_basic_test()
        self.options = mock.Mock()
        # need test project with installed wiki app
        self.options.nbhd = 'Adobe'
        self.options.project = '--init--'

        nbhd = M.Neighborhood.query.get(name=self.options.nbhd)
        h.set_context(self.options.project, 'wiki', neighborhood=nbhd)

        # monkey-patch MediawikiLoader for test
        def pages(self):
            yield 1
            yield 2

        def history(self, page_dir):
            data = {
                1: [
                    {
                        'title': 'Test title',
                        'text': "'''bold''' ''italics''",
                        'page_id': 1,
                        'timestamp': '20120808000001',
                        'username': 'test-user'
                    },
                    {
                        'title': 'Test title',
                        'text': "'''bold'''",
                        'page_id': 1,
                        'timestamp': '20120809000001',
                        'username': 'test-user'
                    },
                ],
                2: [
                    {
                        'title': 'Main',
                        'text': "Main text rev 1",
                        'page_id': 2,
                        'timestamp': '20120808000001',
                        'username': 'bad-user'
                    },
                    {
                        'title': 'Main',
                        'text': "Main text rev 2",
                        'page_id': 2,
                        'timestamp': '20120809000001',
                        'username': 'bad-user'
                    },

                ],
            }
            for page in data[page_dir]:
                yield page

        def talk(self, page_dir):
            data = {
                1: {
                    'text': "''Talk page'' for page 1.",
                    'username': 'test-user',
                    'timestamp': '20120809000001'
                },
                2: {
                    'text': "''Talk page'' for page 2.",
                    'username': 'bad-user',
                    'timestamp': '20120809000001'
                },
            }
            return data[page_dir]

        def attachments(self, *args, **kwargs):
            # make 'empty' iterator
            if False:
                yield

        MediawikiLoader._pages = pages
        MediawikiLoader._history = history
        MediawikiLoader._talk = talk
        MediawikiLoader._attachments = attachments
        self.loader = MediawikiLoader(self.options)

    def get_page(self, title):
        return WM.Page.query.get(app_config_id=context.app.config._id,
                                 title=title)

    def get_post(self, title):
        page = self.get_page(title)
        thread = M.Thread.query.get(ref_id=page.index_id())
        return M.Post.query.get(discussion_id=thread.discussion_id,
                                thread_id=thread._id)

    @skipif(module_not_available('mediawiki'))
    @mock.patch('allura.model.discuss.g.director')
    def test_load_pages(self, director):
        """Test that pages, edit history and talk loaded properly"""
        self.loader.load_pages()
        page = self.get_page('Test title')

        assert page.mod_date == datetime.strptime('20120809000001',
                                                  self.loader.TIMESTAMP_FMT)
        assert page.authors()[0].username == 'test-user'
        assert '**bold**' in page.text
        # _italics should be only in the first revision of page
        assert '_italics_' not in page

        page = page.get_version(1)
        assert '**bold** _italics_' in page.text
        assert page.mod_date == datetime.strptime('20120808000001',
                                                  self.loader.TIMESTAMP_FMT)
        assert page.authors()[0].username == 'test-user'

        page = self.get_page('Main')
        assert page.mod_date == datetime.strptime('20120809000001',
                                                  self.loader.TIMESTAMP_FMT)
        assert page.authors()[0].username == '*anonymous'
        assert 'Main text rev 2' in page.text

        page = page.get_version(1)
        assert page.mod_date == datetime.strptime('20120808000001',
                                                  self.loader.TIMESTAMP_FMT)
        assert page.authors()[0].username == '*anonymous'
        assert 'Main text rev 1' in page.text

        # Check that talk pages loaded
        post = self.get_post('Test title')
        assert post.timestamp == datetime.strptime('20120809000001',
                                                   self.loader.TIMESTAMP_FMT)
        assert post.author().username == 'test-user'
        assert '_Talk page_ for page 1.' in post.text

        post = self.get_post('Main')
        assert post.timestamp == datetime.strptime('20120809000001',
                                                   self.loader.TIMESTAMP_FMT)
        assert post.author().username == '*anonymous'
        assert '_Talk page_ for page 2.' in post.text
