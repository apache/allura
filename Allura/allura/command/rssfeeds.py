import feedparser
import html2text
from bson import ObjectId

import base

from pylons import c

from allura import model as M
from forgeblog import model as BM
from forgeblog import version
from forgeblog.main import ForgeBlogApp 
from allura.lib import exceptions


class RssFeedsCommand(base.Command):
    summary = 'Rss feed client'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-a', '--appid', dest='appid', default='',
                      help='application id')
    parser.add_option('-u', '--username', dest='username', default='root',
                      help='poster username')

    def command(self):
        self.basic_setup()

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

        base.log.info("Get feed: %s" % feed_url)
        f = feedparser.parse(feed_url)
        if f.bozo:
            base.log.exception("%s: %s" % (feed_url, f.bozo_exception))
            return
        for e in f.entries:
            title = e.title
            if 'content' in e:
                content = u''
                for ct in e.content:
                    if ct.type != 'text/html':
                        content = u"%s<p>%s</p>" % (content, ct.value)
                    else:
                        content = content + ct.value
            else:
                content = e.summary

            content = u'%s <a href="%s">link</a>' % (content, e.link)
            content = html2text.html2text(content, e.link)

            post = BM.BlogPost(title=title, text=content, app_config_id=appid,
                               tool_version={'blog': version.__version__},
                               state='draft')
            post.neighborhood_id=c.project.neighborhood_id
            post.make_slug()
            post.commit()
