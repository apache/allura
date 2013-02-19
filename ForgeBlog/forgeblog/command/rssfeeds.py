from time import mktime
from datetime import datetime
import re

import feedparser
from bson import ObjectId

import base
from allura.command import base as allura_base

from ming.orm import session
from pylons import tmpl_context as c

from allura import model as M
from forgeblog import model as BM
from forgeblog import version
from forgeblog.main import ForgeBlogApp
from allura.lib import exceptions
from allura.lib.decorators import exceptionless

## Everything in this file depends on html2text,
## so import attempt is placed in global scope.
try:
    import html2text
except ImportError:
    raise ImportError("""Importing RSS feeds requires GPL library "html2text":
    https://github.com/brondsem/html2text""")

html2text.BODY_WIDTH = 0

re_amp = re.compile(r'''
    [&]          # amp
    (?=          # look ahead for:
      ([a-zA-Z0-9]+;)  # named HTML entity
      |
      (\#[0-9]+;)      # decimal entity
      |
      (\#x[0-9A-F]+;)  # hex entity
    )
    ''', re.VERBOSE)
re_leading_spaces = re.compile(r'^[ ]+', re.MULTILINE)
re_preserve_spaces = re.compile(r'''
    [ ]           # space
    (?=[ ])       # lookahead for a space
    ''', re.VERBOSE)
re_angle_bracket_open = re.compile('<')
re_angle_bracket_close = re.compile('>')
def plain2markdown(text, preserve_multiple_spaces=False, has_html_entities=False):
    if not has_html_entities:
        # prevent &foo; and &#123; from becoming HTML entities
        text = re_amp.sub('&amp;', text)
    # avoid accidental 4-space indentations creating code blocks
    if preserve_multiple_spaces:
        text = text.replace('\t', ' ' * 4)
        text = re_preserve_spaces.sub('&nbsp;', text)
    else:
        text = re_leading_spaces.sub('', text)
    # use html2text for most of the escaping
    text = html2text.escape_md_section(text, snob=True)
    # prevent < and > from becoming tags
    text = re_angle_bracket_open.sub('&lt;', text)
    text = re_angle_bracket_close.sub('&gt;', text)
    return text


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
                    content += plain2markdown(ct.value)
                else:
                    html2md = html2text.HTML2Text(baseurl=e.link)
                    html2md.escape_snob = True
                    markdown_content = html2md.handle(ct.value)
                    content += markdown_content
        else:
            content = plain2markdown(getattr(e, 'summary',
                                        getattr(e, 'subtitle',
                                            getattr(e, 'title'))))

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
