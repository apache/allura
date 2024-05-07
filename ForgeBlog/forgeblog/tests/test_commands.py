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
import html
from datetime import datetime, timedelta
from io import BytesIO
from unittest import skipIf
import pkg_resources
import mock
import feedparser
from mock import patch

from ming.odm.odmsession import ThreadLocalODMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from alluratest.tools import module_not_available
from allura import model as M
from forgeblog import model as BM

test_config = pkg_resources.resource_filename(
    'allura', '../test.ini') + '#main'


def setup_module(module):
    setup_basic_test()
    setup_global_objects()


@skipIf(module_not_available('html2text'), 'requires html2text')
@patch('urllib.request.urlopen')
def test_pull_rss_feeds(urlopen):
    html_content = (
        "<p>1. foo</p>\n"
        "\n"
        "<p>\n"
        "#foo bar <a href='baz'>baz</a>\n"
        "foo bar\n"
        "</p>\n"
        "\n"
        "<p>#foo bar <a href='http://other.com/baz'>\n"
        "baz\n"
        "</a></p>\n"
    )
    html_in_feed = html.escape(html_content).encode('utf-8')

    rendered_html_content = "\n".join([
        r"1\. foo",
        "",
        r"\#foo bar [baz](http://example.com/baz) foo bar",
        "",
        r"\#foo bar [ baz ](http://other.com/baz)",
        "",
        " [link](http://example.com/)",
    ])

    urlopen.return_value = BytesIO(b'''<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Test</title>
      <updated>2003-12-13T18:30:02Z</updated>
      <author><name>John Doe</name></author>
      <subtitle>test</subtitle>
      <summary>This is a test</summary>

      <entry>
        <title>Test summary</title>
        <subtitle>test</subtitle>
        <link href="http://example.com/"/>
        <updated>2003-12-13T18:30:02Z</updated>
        <summary>This is a test</summary>
      </entry>
      <entry>
        <title>Test content</title>
        <link href="http://example.com/"/>
        <updated>2003-12-13T18:30:02Z</updated>
        <content>Test feed</content>
      </entry>
      <entry>
        <title>Test html content</title>
        <link href="http://example.com/"/>
        <updated>2003-12-13T18:30:02Z</updated>
        <content type="html">''' + html_in_feed + b'''</content>
      </entry>
      <entry>
        <title>Test html summary</title>
        <link href="http://example.com/"/>
        <updated>2003-12-13T18:30:02Z</updated>
        <summary type="html">'''+ html_in_feed + b'''</summary>
      </entry>
    </feed>''')

    base_app = M.AppConfig.query.find().all()[0]
    tmp_app = M.AppConfig(
        tool_name='Blog', discussion_id=base_app.discussion_id,
        project_id=base_app.project_id,
        options={'ordinal': 0, 'show_right_bar': True,
                 'project_name': base_app.project.name,
                 'mount_point': 'blog',
                 'mount_label': 'Blog'})
    new_external_feeds = ['http://example.com/news/feed/']
    BM.Globals(app_config_id=tmp_app._id, external_feeds=new_external_feeds)
    ThreadLocalODMSession.flush_all()

    from forgeblog.command import rssfeeds  # importing this sets html2text.BODY_WIDTH to a value this test expects
    cmd = rssfeeds.RssFeedsCommand('pull-rss-feeds')
    cmd.run([test_config, '-a', tmp_app._id])
    cmd.command()
    urlopen.assert_called_with('http://example.com/news/feed/', timeout=None)
    posts = BM.BlogPost.query.find(
        {'app_config_id': tmp_app._id}).sort('timestamp', 1)
    assert posts.count() == 4
    posts = posts.all()
    assert posts[0].title == 'Test summary'
    assert posts[0].text == 'This is a test [link](http://example.com/)'
    assert posts[1].title == 'Test content'
    assert posts[1].text == 'Test feed [link](http://example.com/)'
    assert posts[2].title == 'Test html content'
    assert posts[2].text == rendered_html_content
    assert posts[3].title == 'Test html summary'
    assert posts[3].text == rendered_html_content
