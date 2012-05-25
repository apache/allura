from time import mktime
from datetime import datetime
from HTMLParser import HTMLParser

import feedparser
import html2text
from bson import ObjectId

import base

from ming.orm import session
from pylons import c

from allura import model as M
from forgeblog import model as BM
from forgeblog import version
from forgeblog.main import ForgeBlogApp 
from allura.lib import exceptions

html2text.BODY_WIDTH = 0

class MDHTMLParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.NO_END_TAGS = ["area", "base", "basefont", "br", "col", "frame",
                            "hr", "img", "input", "link", "meta", "param"]
        self.CUSTTAG_OPEN = u"[plain]"
        self.CUSTTAG_CLOSE = u"[/plain]"
        self.result_doc = u""
        self.custom_tag_opened = False

    def handle_starttag(self, tag, attrs):
        if self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_CLOSE)
            self.custom_tag_opened = False

        tag_text = u"<%s" % tag
        for attr in attrs:
            if attr[1].find('"'):
                tag_text = u"%s %s='%s'" % (tag_text, attr[0], attr[1])
            else:
                tag_text = u'%s %s="%s"' % (tag_text, attr[0], attr[1])
        if tag not in self.NO_END_TAGS:
            tag_text = tag_text + ">"
        else:
            tag_text = tag_text + "/>"
        self.result_doc = u"%s%s" % (self.result_doc, tag_text)

    def handle_endtag(self, tag):
        if tag not in self.NO_END_TAGS:
            if self.custom_tag_opened:
                self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_CLOSE)
                self.custom_tag_opened = False

            self.result_doc = u"%s</%s>" % (self.result_doc, tag)

    def handle_data(self, data):
        if len(data.split()) == 0:
            self.result_doc = u"%s%s" % (self.result_doc, data)
            return

        res_data = ""
        for line in data.split('\n'):
            if self.custom_tag_opened:
                res_data = u"%s%s" % (res_data, self.CUSTTAG_CLOSE)
                self.custom_tag_opened = False

            if len(line.split()) > 0:
                res_data = u"%s\n%s%s" % (res_data, self.CUSTTAG_OPEN, line)
                self.custom_tag_opened = True
            else:
                res_data = u"%s\n" % res_data

        if data[-1:] == "\n" and self.custom_tag_opened:
            res_data = u"%s%s" % (res_data, self.CUSTTAG_CLOSE)
            self.custom_tag_opened = False

        self.result_doc = u"%s%s" % (self.result_doc, res_data)

    def handle_comment(self, data):
        if self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_CLOSE)
            self.custom_tag_opened = False

        self.result_doc = u"%s<!-- %s -->" % (self.result_doc, data)

    def handle_entityref(self, name):
        if not self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_OPEN)
            self.custom_tag_opened = True

        self.result_doc = u"%s&%s;" % (self.result_doc, name)

    def handle_charref(self, name):
        if not self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_OPEN)
            self.custom_tag_opened = True

        self.result_doc = u"%s&%s;" % (self.result_doc, name)

    def handle_decl(self, data):
        if self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_CLOSE)
            self.custom_tag_opened = False

        self.result_doc = u"%s<!%s>" % (self.result_doc, data)

    def close(self):
        HTMLParser.close(self)

        if self.custom_tag_opened:
            self.result_doc = u"%s%s" % (self.result_doc, self.CUSTTAG_CLOSE)
            self.custom_tag_opened = False


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
                # TODO remove me
                feed_url = 'https://twitter.com/statuses/user_timeline/openatadobe.atom'
                self.process_feed(appid, feed_url)
                # TODO remove me
                break

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
            parser = MDHTMLParser()
            parser.feed(content)
            parser.close()
            content = html2text.html2text(parser.result_doc, e.link)

            updated = datetime.fromtimestamp(mktime(e.updated_parsed))

            base_slug = BM.BlogPost.make_base_slug(title, updated, feed_url)
            b_count = BM.BlogPost.query.find(dict(slug=base_slug)).count()
            if b_count == 0:
                post = BM.BlogPost(title=title, text=content, timestamp=updated,
                               app_config_id=appid,
                               tool_version={'blog': version.__version__},
                               state='published')
                post.neighborhood_id=c.project.neighborhood_id
                post.make_slug(source=feed_url)
                post.commit()

        session(BM.BlogPost).flush()

# paster pull-rss-feeds development.ini -a 4facfec6610b271748000005
