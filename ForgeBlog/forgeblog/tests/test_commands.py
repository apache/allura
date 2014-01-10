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

from datetime import datetime, timedelta
from pylons import app_globals as g
from datadiff.tools import assert_equal
from IPython.testing.decorators import module_not_available, skipif
import pkg_resources
import mock
import feedparser

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from forgeblog import model as BM


test_config = pkg_resources.resource_filename(
    'allura', '../test.ini') + '#main'


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
            updated=datetime.utcnow() + timedelta(days=_mock_feed.i - 100))
        entry.update(e)
        entry['updated_parsed'] = entry['updated'].timetuple()
        if 'content' in entry:
            entry['content'] = [
                attrdict(type=entry['content_type'], value=entry['content'])]
        if 'summary_detail' in entry:
            entry['summary_detail'] = attrdict(entry['summary_detail'])
        feed.entries.append(entry)

    return feed
_mock_feed.i = 0


@skipif(module_not_available('html2text'))
@mock.patch.object(feedparser, 'parse')
def test_pull_rss_feeds(parsefeed):
    html_content = (
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
    )

    rendered_html_content = "\n".join([
        r"1\. foo",
        "",
        r"\#foo bar [baz](baz) foo bar ",
        "",
        r"\#foo bar [ baz ](baz)",
        " [link](http://example.com/)",
    ])

    parsefeed.return_value = _mock_feed(
        dict(title='Test', subtitle='test', summary='This is a test'),
        dict(content_type='text/plain', content='Test feed'),
        dict(content_type='text/html', content=html_content),
        dict(summary_detail=dict(type='text/html', value=html_content)),
    )

    base_app = M.AppConfig.query.find().all()[0]
    tmp_app = M.AppConfig(
        tool_name=u'Blog', discussion_id=base_app.discussion_id,
        project_id=base_app.project_id,
        options={u'ordinal': 0, u'show_right_bar': True,
                 u'project_name': base_app.project.name,
                 u'mount_point': u'blog',
                 u'mount_label': u'Blog'})
    new_external_feeds = ['http://example.com/news/feed/']
    BM.Globals(app_config_id=tmp_app._id, external_feeds=new_external_feeds)
    ThreadLocalORMSession.flush_all()

    from forgeblog.command import rssfeeds
    cmd = rssfeeds.RssFeedsCommand('pull-rss-feeds')
    cmd.run([test_config, '-a', tmp_app._id])
    cmd.command()
    parsefeed.assert_called_with('http://example.com/news/feed/')
    posts = BM.BlogPost.query.find(
        {'app_config_id': tmp_app._id}).sort('timestamp', 1)
    assert_equal(posts.count(), 4)
    posts = posts.all()
    assert_equal(posts[0].title, 'Test')
    assert_equal(posts[0].text, 'This is a test [link](http://example.com/)')
    assert_equal(posts[1].title, 'Default Title 2')
    assert_equal(posts[1].text, 'Test feed [link](http://example.com/)')
    assert_equal(posts[2].title, 'Default Title 3')
    assert_equal(posts[2].text, rendered_html_content)
    assert_equal(posts[3].title, 'Default Title 4')
    assert_equal(posts[3].text, rendered_html_content)


@skipif(module_not_available('html2text'))
def test_plaintext_preprocessor():
    from html2text import html2text
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
                 '#foo bar <a class="" href="../baz">baz</a> foo bar '
                 '#foo bar <a class="" href="../baz"> baz </a></p></div>'
                 )


@skipif(module_not_available('html2text'))
def test_plaintext_preprocessor_wrapped():
    from html2text import html2text
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
                 '<div class="markdown_content"><p>1. foo</p>\n'
                 '<p>#foo bar <a class="" href="../baz">baz</a> foo bar </p>\n'
                 '<p>#foo bar <a class="" href="../baz"> baz </a></p></div>'
                 )
