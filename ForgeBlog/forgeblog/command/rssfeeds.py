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

import calendar
from datetime import datetime

import feedparser
from bson import ObjectId

from . import base
from allura.command import base as allura_base

from ming.orm import session
from tg import tmpl_context as c

from allura import model as M
from forgeblog import model as BM
from forgeblog.main import ForgeBlogApp
from allura.lib import exceptions
from allura.lib.helpers import exceptionless
from allura.lib.helpers import plain2markdown
from allura.lib.utils import socket_default_timeout

# Everything in this file depends on html2text,
# so import attempt is placed in global scope.
try:
    import html2text
except ImportError:
    raise ImportError("""Importing RSS feeds requires GPL library "html2text":
    https://github.com/brondsem/html2text""")

html2text.BODY_WIDTH = 0


class RssFeedsCommand(base.BlogCommand):
    summary = 'Fetch external rss feeds for all Blog tools, and convert new feed entries into blog posts'
    parser = base.BlogCommand.standard_parser(verbose=True)
    parser.add_option('-a', '--appid', dest='appid', default='',
                      help='application id')
    parser.add_option('-u', '--username', dest='username', default='root',
                      help='poster username')

    def command(self):
        self.basic_setup()

        # If this script creates a new BlogPost, it will create an
        # activitystream activity for that post. During the saving of the
        # activity, User.url() will be called. This method defers to an
        # AuthenticationProvider, which depends on a request being setup in
        # the current thread. So, we set one up here.
        import tg
        import webob
        tg.request_local.context.request = webob.Request.blank('/')

        self.process_feed = exceptionless(
            None, log=allura_base.log)(self.process_feed)
        self.process_entry = exceptionless(
            None, log=allura_base.log)(self.process_entry)

        user = M.User.query.get(username=self.options.username)
        c.user = user

        with socket_default_timeout(20):
            self.prepare_feeds()
            for appid in self.feed_dict:
                for feed_url in self.feed_dict[appid]:
                    self.process_feed(appid, feed_url)

    def prepare_feeds(self):
        feed_dict = {}
        if self.options.appid != '':
            gl_app = BM.Globals.query.get(
                app_config_id=ObjectId(self.options.appid))
            if not gl_app:
                raise exceptions.NoSuchGlobalsError("The globals %s "
                                                    "could not be found in the database" % self.options.appid)
            if len(gl_app.external_feeds) > 0:
                feed_dict[gl_app.app_config_id] = gl_app.external_feeds
        else:
            for gl_app in BM.Globals.query.find().all():
                if len(gl_app.external_feeds) > 0:
                    feed_dict[gl_app.app_config_id] = gl_app.external_feeds
        self.feed_dict = feed_dict

    def process_feed(self, appid, feed_url):
        appconf = M.AppConfig.query.get(_id=appid)
        if not appconf:
            return

        c.project = appconf.project
        app = ForgeBlogApp(c.project, appconf)
        c.app = app

        allura_base.log.info(f"Getting {app.url} feed {feed_url}")
        f = feedparser.parse(feed_url)
        if f.bozo:
            allura_base.log.warn(f"{app.url} feed {feed_url} errored: {f.bozo_exception}")
            return
        for e in f.entries:
            self.process_entry(e, appid)
        session(BM.BlogPost).flush()

    def process_entry(self, e, appid):
        title = e.title
        allura_base.log.info(" ...entry '%s'", title)
        parsed_content = [_f for _f in e.get('content') or [e.get('summary_detail')] if _f]
        if parsed_content:
            content = ''
            for ct in parsed_content:
                if ct.type != 'text/html':
                    content += plain2markdown(ct.value)
                else:
                    html2md = html2text.HTML2Text(baseurl=e.link)
                    html2md.escape_snob = True
                    markdown_content = html2md.handle(ct.value)
                    content += markdown_content
        else:
            content = plain2markdown(getattr(e, 'summary',
                                             getattr(e, 'subtitle',
                                                     e.title)))

        content += ' [link](%s)' % e.link
        updated = datetime.utcfromtimestamp(calendar.timegm(e.updated_parsed))

        base_slug = BM.BlogPost.make_base_slug(title, updated)
        b_count = BM.BlogPost.query.find(
            dict(slug=base_slug, app_config_id=appid)).count()
        if b_count == 0:
            post = BM.BlogPost(title=title, text=content, timestamp=updated,
                               app_config_id=appid,
                               state='published')
            post.neighborhood_id = c.project.neighborhood_id
            post.make_slug()
            post.commit()
