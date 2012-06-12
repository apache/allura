import mock

from forgewiki.command.wiki2markdown.extractors import MySQLExtractor
from forgewiki.command.wiki2markdown.loaders import MediawikiLoader
from alluratest.controller import setup_basic_test
from allura import model as M
from forgewiki import model as WM
from allura.lib import helpers as h

import pylons
pylons.c = pylons.tmpl_context
from pylons import c as context


class TestMySQLExtractor(object):

    def setUp(self):
        setup_basic_test()
        self.options = mock.Mock()
        self.options.dump_dir = '/tmp/w2m_test'

        # monkey-patch MySQLExtractor for test
        def pages(self):
            # yield (page_id, page_data)
            yield 1, {'title': 'Test title', 'text': 'Test Text'}
            yield 2, {'title': 'Main_Page', 'text': 'Main_page text'}
            yield 3, {'title': 'Test', 'text': ''}

        MySQLExtractor._pages = pages
        self.extractor = MySQLExtractor(self.options)

    def test_extract_pages(self):
        self.extractor.extract_pages()

        with open('/tmp/w2m_test/pages/1.json', 'r') as f:
            json_page = f.read()
        assert json_page == '{"text": "Test Text", "title": "Test title"}'

        with open('/tmp/w2m_test/pages/2.json', 'r') as f:
            json_page = f.read()
        assert json_page == '{"text": "Main_page text", "title": "Main_Page"}'

        with open('/tmp/w2m_test/pages/3.json', 'r') as f:
            json_page = f.read()
        assert json_page == '{"text": "", "title": "Test"}'


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
            yield {'title': 'Test title', 'text': "'''bold''' ''italics''"}
            yield {'title': 'Main', 'text': "main"}
            yield {'title': 'Test', 'text': 'test'}

        MediawikiLoader._pages = pages
        self.loader = MediawikiLoader(self.options)

    def get_page(self, title):
        return WM.Page.query.get(app_config_id=context.app.config._id,
                                 title=title)

    def test_load_pages(self):
        self.loader.load_pages()
        page = self.get_page('Test title')
        assert '**bold** _italics_' in page.text

        page = self.get_page('Main')
        assert 'main' in page.text

        page = self.get_page('Test')
        print page.text, len(page.text)
        assert 'test' in page.text
