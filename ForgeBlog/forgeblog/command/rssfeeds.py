from time import mktime
from datetime import datetime

import feedparser
import html2text
from bson import ObjectId

import base
from allura.command import base as allura_base

from ming.orm import session
from pylons import c

from allura import model as M
from forgeblog import model as BM
from forgeblog import version
from forgeblog.main import ForgeBlogApp
from allura.lib import exceptions
from allura.lib.decorators import exceptionless

html2text.BODY_WIDTH = 0


class RssFeedsCommand(base.BlogCommand):
    summary = 'Rss feed client'
    parser = base.BlogCommand.standard_parser(verbose=True)
    parser.add_option('-a', '--appid', dest='appid', default='',
                      help='application id')
    parser.add_option('-u', '--username', dest='username', default='root',
                      help='poster username')

    def command(self):
        # If this script creates a new BlogPost, it will create an
        # activitystream activity for that post. During the saving of the
        # activity, User.url() will be called. This method defers to an
        # AuthenticationProvider, which depends on a request being setup in
        # the current thread. So, we set one up here.
        import pylons, webob
        pylons.request._push_object(webob.Request.blank('/'))

        self.basic_setup()
        self.process_feed = exceptionless(None, log=allura_base.log)(self.process_feed)
        self.process_entry = exceptionless(None, log=allura_base.log)(self.process_entry)

        user = M.User.query.get(username=self.options.username)
        c.user = user

        self.prepare_feeds()
        for appid in self.feed_dict:
            for feed_url in self.feed_dict[appid]:
                self.process_feed(appid, feed_url)

    def prepare_feeds(self):
        feed_dict = {}
        if self.options.appid != '':
            gl_app = BM.Globals.query.get(app_config_id=ObjectId(self.options.appid))
            if not gl_app:
                raise exceptions.NoSuchGlobalsError("The globals %s " \
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

        allura_base.log.info("Get feed: %s" % feed_url)
        f = feedparser.parse(feed_url)
        if f.bozo:
            allura_base.log.exception("%s: %s" % (feed_url, f.bozo_exception))
            return
        for e in f.entries:
            self.process_entry(e, appid)
        session(BM.BlogPost).flush()

    def process_entry(self, e, appid):
        title = e.title
        allura_base.log.info(" ...entry '%s'", title)
        if 'content' in e:
            content = u''
            for ct in e.content:
                if ct.type != 'text/html':
                    content += html2text.escape_md_section(ct.value, snob=True)
                else:
                    html2md = html2text.HTML2Text(baseurl=e.link)
                    html2md.escape_snob = True
                    markdown_content = html2md.handle(ct.value)
                    content += markdown_content
        else:
            content = html2text.escape_md_section(getattr(e, 'summary',
                                                    getattr(e, 'subtitle',
                                                      getattr(e, 'title'))),
                                                  snob=True)

        content += u' [link](%s)' % e.link
        updated = datetime.utcfromtimestamp(mktime(e.updated_parsed))

        base_slug = BM.BlogPost.make_base_slug(title, updated)
        b_count = BM.BlogPost.query.find(dict(slug=base_slug, app_config_id=appid)).count()
        if b_count == 0:
            post = BM.BlogPost(title=title, text=content, timestamp=updated,
                            app_config_id=appid,
                            tool_version={'blog': version.__version__},
                            state='published')
            post.neighborhood_id=c.project.neighborhood_id
            post.make_slug()
            post.commit()
