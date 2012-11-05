from datetime import datetime, timedelta
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g
from nose.tools import assert_equal

from html2text import html2text

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import security
from allura.lib import helpers as h
from forgeblog import model as BM
from forgeblog.command import rssfeeds

import mock


test_config = 'test.ini#main'

def setUp():
    setup_basic_test()
    setup_global_objects()

def _mock_feed(*entries):
    class attrdict(dict):
        def __getattr__(self, name):
            return self[name]

    feed = mock.Mock()
    feed.bozo = False
    feed.entries = []
    for e in entries:
        _mock_feed.i += 1
        entry = attrdict(
            content_type='text/plain',
            title='Default Title %d' % _mock_feed.i,
            subtitle='',
            summary='',
            link='http://example.com/',
            updated=datetime.utcnow()+timedelta(days=_mock_feed.i - 100))
        entry.update(e)
        entry['updated_parsed'] = entry['updated'].timetuple()
        if 'content' in entry:
            entry['content'] = [attrdict(type=entry['content_type'], value=entry['content'])]
        feed.entries.append(entry)

    return feed
_mock_feed.i = 0

@mock.patch.object(rssfeeds.feedparser, 'parse')
def test_pull_rss_feeds(parsefeed):
    parsefeed.return_value = _mock_feed(
        dict(title='Test', subtitle='test', summary='This is a test'),
        dict(content_type='text/plain', content='Test feed'),
        dict(content_type='text/html', content=
                "<p>1. foo</p>\n"
                "\n"
                "<p>\n"
                "#foo bar <a href='baz'>baz</a>\n"
                "foo bar\n"
                "</p>\n"
                "\n"
                "<p>#foo bar <a href='baz'>\n"
                "baz\n"
                "</a></p>\n"
            ),
    )

    base_app =  M.AppConfig.query.find().all()[0]
    tmp_app = M.AppConfig(tool_name=u'Blog', discussion_id=base_app.discussion_id,
                          project_id=base_app.project_id,
                          options={u'ordinal': 0, u'show_right_bar': True,
                                    u'project_name': base_app.project.name,
                                    u'mount_point': u'blog',
                                    u'mount_label': u'Blog'})
    new_external_feeds = ['http://example.com/news/feed/']
    BM.Globals(app_config_id=tmp_app._id, external_feeds=new_external_feeds)
    ThreadLocalORMSession.flush_all()

    cmd = rssfeeds.RssFeedsCommand('pull-rss-feeds')
    cmd.run([test_config, '-a', tmp_app._id])
    cmd.command()
    parsefeed.assert_called_with('http://example.com/news/feed/')
    posts = BM.BlogPost.query.find({'app_config_id': tmp_app._id}).sort('timestamp', 1)
    assert_equal(posts.count(), 3)
    posts = posts.all()
    assert_equal(posts[0].title, 'Test')
    assert_equal(posts[0].text, 'This is a test [link](http://example.com/)')
    assert_equal(posts[1].title, 'Default Title 2')
    assert_equal(posts[1].text, 'Test feed [link](http://example.com/)')
    assert_equal(posts[2].title, 'Default Title 3')
    assert_equal(posts[2].text, "\n".join([
       r"1\. foo",
        "",
       r"\#foo bar [baz](baz) foo bar ",
        "",
       r"\#foo bar [ baz ](baz)",
        " [link](http://example.com/)",
    ]))

def test_plaintext_preprocessor():
    text = html2text(
        "[plain]1. foo[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>[plain]baz[/plain]</a>\n"
        "[plain]foo bar[/plain]\n"
        "\n"
        "[plain]#foo bar [/plain]<a href='baz'>\n"
        "[plain]baz[/plain]\n"
        "</a>\n"
    )
    html = g.markdown.convert(text)
    assert_equal(html,
        '<div class="markdown_content"><p>1. foo '
        '#foo bar <a href="../baz">baz</a> foo bar '
        '#foo bar <a href="../baz"> baz </a></p></div>'
    )

def test_plaintext_preprocessor_wrapped():
    text = html2text(
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
    html = g.markdown.convert(text)
    assert_equal(html,
        '<div class="markdown_content">1. foo\n'
        '\n'
        '<p>#foo bar <a href="../baz">baz</a> foo bar </p>\n'
        '<p>#foo bar <a href="../baz"> baz </a></p></div>'
    )
