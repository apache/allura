import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g
from nose.tools import assert_equal

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import security
from allura.lib import helpers as h
from forgeblog import model as BM
from forgeblog.command import rssfeeds

test_config = 'test.ini#main'

def setUp():
    setup_basic_test()
    setup_global_objects()

def test_pull_rss_feeds():
    base_app =  M.AppConfig.query.find().all()[0]
    tmp_app = M.AppConfig(tool_name=u'Blog', discussion_id=base_app.discussion_id,
                          project_id=base_app.project_id,
                          options={u'ordinal': 0, u'show_right_bar': True,
                                    u'project_name': base_app.project.name,
                                    u'mount_point': u'blog',
                                    u'mount_label': u'Blog'})
    new_external_feeds = ['http://wordpress.org/news/feed/']
    BM.Globals(app_config_id=tmp_app._id, external_feeds=new_external_feeds)
    ThreadLocalORMSession.flush_all()

    cmd = rssfeeds.RssFeedsCommand('pull-rss-feeds')
    cmd.run([test_config, '-a', tmp_app._id])
    cmd.command()
    assert len(BM.BlogPost.query.find({'app_config_id': tmp_app._id}).all()) > 0

def test_plaintext_parser():
    parser = rssfeeds.MDHTMLParser()
    parser.feed(
        '1. foo\n'
        '\n'
        '#foo bar <a href="baz">baz</a>\n'
        'foo bar\n'
        '\n'
        '#foo bar <a href="baz">\n'
        'baz\n'
        '</a>\n'
    )
    parser.close()
    assert_equal(parser.result_doc,
        "[plain]1. foo[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>[plain]baz[/plain]</a>\n"
        "[plain]foo bar[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>\n"
        "[plain]baz[/plain]\n"
        "</a>\n"
    )

def test_plaintext_parser_wrapped():
    parser = rssfeeds.MDHTMLParser()
    parser.feed(
        '<p>1. foo</p>\n'
        '\n'
        '<p>\n'
        '#foo bar <a href="baz">baz</a>\n'
        'foo bar\n'
        '</p>\n'
        '\n'
        '<p>#foo bar <a href="baz">\n'
        'baz\n'
        '</a></p>\n'
    )
    parser.close()
    assert_equal(parser.result_doc,
        "<p>[plain]1. foo[/plain]</p>\n"
        "\n"
        "<p>\n"
        "[plain]#foo bar [/plain]<a href='baz'>[plain]baz[/plain]</a>\n"
        "[plain]foo bar[/plain]\n"
        "</p>\n"
        "\n"
        "<p>[plain]#foo bar [/plain]<a href='baz'>\n"
        "[plain]baz[/plain]\n"
        "</a></p>\n"
    )

def test_plaintext_preprocessor():
    html = g.markdown.convert(
        "[plain]1. foo[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>[plain]baz[/plain]</a>\n"
        "[plain]foo bar[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>\n"
        "[plain]baz[/plain]\n"
        "</a>\n"
    )
    assert_equal(html,
        '<div class="markdown_content">'
        '1. foo\n'
        '\n'
        '<p>'
        '#foo bar <a href="../baz">baz</a><br />'
        'foo bar'
        '</p><p>'
        '#foo bar <a href="../baz"><br />'
        'baz<br />'
        '</a>'
        '</p></div>'
    )

def test_plaintext_preprocessor_wrapped():
    html = g.markdown.convert(
        "<p>[plain]1. foo[/plain]</p>\n"
        "\n"
        "<p>\n"
        "[plain]#foo bar [/plain]<a href='baz'>[plain]baz[/plain]</a>\n"
        "[plain]foo bar[/plain]\n"
        "</p>\n"
        "\n"
        "<p>[plain]#foo bar [/plain]<a href='baz'>\n"
        "[plain]baz[/plain]\n"
        "</a></p>\n"
    )
    assert_equal(html,
        '<div class="markdown_content">'
        '<p>1. foo</p>\n'
        '\n'
        '<p>\n'
        '#foo bar <a href="../baz">baz</a>\n'
        'foo bar\n'
        '</p>\n'
        '<p>#foo bar <a href="../baz">\n'
        'baz\n'
        '</a></p>\n'
        '</div>'
    )
