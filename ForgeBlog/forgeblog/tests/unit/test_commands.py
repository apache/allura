from forgeblog.command.rssfeeds import MDHTMLParser


class TestMDHTMLParser(object):

    def test_handle_starttag(self):
        parser = MDHTMLParser()

        tag = 'img'
        attrs = [('src', 'img.jpg')]
        img_result = '<img src="img.jpg"/>'
        parser.handle_starttag(tag, attrs)
        assert parser.result_doc == img_result

        tag = 'a'
        attrs = [
            ('href', 'http://google.com'),
            ('onclick', 'javascript: alert("Click");')
        ]
        a_result = ('<a href="http://google.com"'
                    ' onclick=\'javascript: alert("Click");\'>')
        parser.custom_tag_opened = True
        parser.result_doc = ''
        parser.handle_starttag(tag, attrs)
        assert not parser.custom_tag_opened
        assert parser.result_doc == '%s%s' % ('[/plain]', a_result)

    def test_handle_endtag(self):
        parser = MDHTMLParser()

        parser.handle_endtag('a')
        assert parser.result_doc == '</a>'

        parser.result_doc = ''
        parser.custom_tag_opened = True
        parser.handle_endtag('div')
        assert not parser.custom_tag_opened
        assert parser.result_doc == '[/plain]</div>'

    def test_handle_data(self):
        parser = MDHTMLParser()

        data = '   \t   \n '
        parser.handle_data(data)
        assert parser.result_doc == data

        parser.result_doc = ''
        data = '**some**\nmultiline\ndata with spaces \n'
        result = """
[plain]**some**[/plain]
[plain]multiline[/plain]
[plain]data with spaces [/plain]
"""
        parser.handle_data(data)
        assert parser.result_doc == result

        parser.result_doc = ''
        parser.custom_tag_opened = True
        data = "another\n'''data''' \n"
        result = """[/plain]
[plain]another[/plain]
[plain]'''data''' [/plain]
"""
        parser.handle_data(data)
        assert parser.result_doc == result
        assert not parser.custom_tag_opened

    def test_handle_comment(self):
        parser = MDHTMLParser()

        parser.handle_comment('some comment text')
        assert parser.result_doc == '<!-- some comment text -->'

        parser.result_doc = ''
        parser.custom_tag_opened = True
        parser.handle_comment('another comment')
        assert not parser.custom_tag_opened
        assert parser.result_doc == '[/plain]<!-- another comment -->'

    def test_handle_entityref(self):
        parser = MDHTMLParser()

        parser.custom_tag_opened = True
        parser.handle_entityref('gt')
        assert parser.result_doc == '&gt;'
        assert parser.custom_tag_opened

        parser.result_doc = ''
        parser.custom_tag_opened = False
        parser.handle_entityref('lt')
        assert parser.result_doc == '[plain]&lt;'
        assert parser.custom_tag_opened

    def test_handle_charref(self):
        parser = MDHTMLParser()

        parser.custom_tag_opened = True
        parser.handle_charref('62')
        assert parser.result_doc == '&#62;'
        assert parser.custom_tag_opened

        parser.result_doc = ''
        parser.custom_tag_opened = False
        parser.handle_charref('x3E')
        assert parser.result_doc == '[plain]&#x3E;'
        assert parser.custom_tag_opened

    def test_handle_decl(self):
        parser = MDHTMLParser()

        parser.handle_decl('DOCTYPE html')
        assert parser.result_doc == '<!DOCTYPE html>'

        parser.result_doc = ''
        parser.custom_tag_opened = True
        parser.handle_decl('DOCTYPE html')
        assert parser.result_doc == '[/plain]<!DOCTYPE html>'
        assert not parser.custom_tag_opened
