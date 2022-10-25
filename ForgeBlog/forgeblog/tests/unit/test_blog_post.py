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

from datetime import datetime
from tg import tmpl_context as c

from forgeblog import model as M
from forgeblog.tests.unit import BlogTestWithModel
from allura.model import Feed


def wrapped(s):
    return '<div class="markdown_content"><p>%s</p></div>' % s


class TestBlogPost(BlogTestWithModel):

    def test_new(self):
        post = M.BlogPost.new(
            title='test', text='test message', state='published')
        assert post.title == 'test'
        assert post.text == 'test message'
        assert post.state == 'published'
        assert post.activity_extras['summary'] == post.title
        assert 'allura_id' in post.activity_extras


class TestFeed(BlogTestWithModel):

    def testd(self):
        post = M.BlogPost()
        post.title = 'test'
        post.text = 'test message'
        post.state = 'published'
        post.timestamp = datetime(2012, 10, 29, 9, 57, 21, 465000)
        post.neighborhood_id = c.project.neighborhood_id
        post.make_slug()
        post.commit()
        f = Feed.post(
            post,
            title=post.title,
            description=post.text,
            author=post.author(),
            pubdate=post.timestamp)
        assert f.pubdate == datetime(2012, 10, 29, 9, 57, 21, 465000)


class TestHtmlPreview(BlogTestWithModel):

    def _make_post(self, text):
        post = M.BlogPost()
        post.text = text
        post.make_slug()
        return post

    def test_single_long_paragraph(self):
        text = ("Lorem ipsum dolor sit amet, consectetur adipisicing elit, "
                "sed do eiusmod tempor incididunt ut labore et dolore magna "
                "aliqua. Ut enim ad minim veniam, quis nostrud exercitation "
                "ullamco laboris nisi ut aliquip ex ea commodo consequat. "
                "Duis aute irure dolor in reprehenderit in voluptate velit "
                "esse cillum dolore eu fugiat nulla pariatur. Excepteur sint "
                "occaecat cupidatat non proident, sunt in culpa qui officia "
                "deserunt mollit anim id est laborum.")
        assert self._make_post(text).html_text_preview == wrapped(text)

    def test_single_short_paragraph(self):
        text = ("Lorem ipsum dolor sit amet, consectetur adipisicing elit, "
                "sed do eiusmod tempor incididunt ut labore et dolore magna "
                "aliqua. Ut enim ad minim veniam, quis nostrud exercitation "
                "ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        assert self._make_post(text).html_text_preview == wrapped(text)

    def test_multi_paragraph_short(self):
        text = ("Lorem ipsum dolor sit amet, consectetur adipisicing elit, "
                "sed do eiusmod tempor incididunt ut labore et dolore magna "
                "aliqua."
                "\n\n"
                "Ut enim ad minim veniam, quis nostrud exercitation "
                "ullamco laboris nisi ut aliquip ex ea commodo consequat.")

        expected = ('<div class="markdown_content"><p>Lorem ipsum dolor sit '
                    'amet, consectetur adipisicing elit, sed do eiusmod '
                    'tempor incididunt ut labore et dolore magna aliqua.</p>\n'
                    '<p>Ut enim ad minim veniam, quis nostrud exercitation '
                    'ullamco laboris nisi ut aliquip ex ea commodo '
                    'consequat.</p></div>')
        assert self._make_post(text).html_text_preview == expected

    def test_multi_paragraph_long(self):
        text = ("Lorem ipsum dolor sit amet, consectetur adipisicing elit, "
                "sed do eiusmod tempor incididunt ut labore et dolore magna "
                "aliqua."
                "\n\n"
                "Lorem ipsum dolor sit amet, consectetur adipisicing elit, "
                "sed do eiusmod tempor incididunt ut labore et dolore magna "
                "aliqua. Ut enim ad minim veniam, quis nostrud exercitation "
                "ullamco laboris nisi ut aliquip ex ea commodo consequat. "
                "Duis aute irure dolor in reprehenderit in voluptate velit "
                "esse cillum dolore eu fugiat nulla pariatur. Excepteur sint "
                "occaecat cupidatat non proident, sunt in culpa qui officia "
                "deserunt mollit anim id est laborum."
                "\n\n"
                "Ut enim ad minim veniam, quis nostrud exercitation "
                "ullamco laboris nisi ut aliquip ex ea commodo consequat.")

        now = datetime.utcnow()
        expected = ('<div class="markdown_content"><p>Lorem ipsum dolor sit '
                    'amet, consectetur adipisicing elit, sed do eiusmod '
                    'tempor incididunt ut labore et dolore magna aliqua.</p>\n'
                    '<p>Lorem ipsum dolor sit amet, consectetur adipisicing '
                    'elit, sed do eiusmod tempor incididunt ut labore et '
                    'dolore magna aliqua. Ut enim ad minim veniam, quis '
                    'nostrud exercitation ullamco laboris nisi ut aliquip ex '
                    'ea commodo consequat. Duis aute irure dolor in '
                    'reprehenderit in voluptate velit esse cillum dolore eu '
                    'fugiat nulla pariatur. Excepteur sint occaecat cupidatat '
                    'non proident, sunt in culpa qui officia deserunt mollit '
                    'anim id est laborum.... '
                    '<a class="" href="/p/test/blog/%s/%02i/untitled/">'
                    'read more</a></p></div>') % (now.year, now.month)
        assert self._make_post(text).html_text_preview == expected
