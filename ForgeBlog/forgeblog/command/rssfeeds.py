from time import mktime
from datetime import datetime
from HTMLParser import HTMLParser

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
        res_data = ''

        for line in data.splitlines(True):
            # pre-emptive special case
            if not line or line.isspace():
                # don't wrap all whitespace lines
                res_data += line
                continue

            # open custom tag
            if not self.custom_tag_opened:
                res_data += self.CUSTTAG_OPEN
                self.custom_tag_opened = True
            # else: cust tag might be open already from previous incomplete data block

            # data
            res_data += line.rstrip('\r\n')  # strip EOL (add close tag before)

            # close custom tag
            if line.endswith(('\r','\n')):
                res_data += self.CUSTTAG_CLOSE + '\n'
                self.custom_tag_opened = False
            # else: no EOL could mean we're dealing with incomplete data block;
                # leave it open for next handle_data, handle_starttag, or handle_endtag to clean up

        self.result_doc += res_data

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


class RssFeedsCommand(base.BlogCommand):
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

        allura_base.log.info("Get feed: %s" % feed_url)
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
                        content += '[plain]%s[/plain]' % ct.value
                    else:
                        if False:
                            # FIXME: disabled until https://sourceforge.net/p/allura/tickets/4345
                            # because the bad formatting from [plain] is worse than bad formatting from unintentional markdown syntax
                            parser = MDHTMLParser()
                            parser.feed(ct.value)
                            parser.close() # must be before using the result_doc
                            markdown_content = html2text.html2text(parser.result_doc, baseurl=e.link)
                        else:
                            markdown_content = html2text.html2text(ct.value, baseurl=e.link)

                        content += markdown_content
            else:
                content = '[plain]%s[/plain]' % getattr(e, 'summary',
                                                    getattr(e, 'subtitle',
                                                        getattr(e, 'title')))

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

        session(BM.BlogPost).flush()
