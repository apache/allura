import logging

from pylons import request
from pylons import tmpl_context as c

from allura.lib import helpers as h
from allura.lib.spam import SpamFilter

import akismet


log = logging.getLogger(__name__)


class AkismetSpamFilter(SpamFilter):
    """Spam checking implementation via Akismet service.

    To enable Akismet spam filtering in your Allura instance, first
    enable the entry point in setup.py::

        [allura.spam]
        akismet = allura.lib.spam.akismetfilter:AkismetSpamFilter

    Then include the following parameters in your .ini file::

        spam.method = akismet
        spam.key = <your Akismet key here>
    """
    def __init__(self, config):
        self.service = akismet.Akismet(config.get('spam.key'), config.get('base_url'))
        self.service.verify_key()

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        log_msg = text
        kw['comment_content'] = text
        kw['comment_type'] = content_type
        if artifact:
            kw['permalink'] = artifact.url()
            log_msg = artifact.url()
        user = user or c.user
        if user:
            kw['comment_author'] = user.display_name or user.username
            kw['comment_author_email'] = user.email_addresses[0] if user.email_addresses else ''
        user_ip = request.headers.get('X_FORWARDED_FOR', request.remote_addr)
        kw['user_ip'] = user_ip.split(',')[0].strip()
        kw['user_agent'] = request.headers.get('USER_AGENT')
        kw['referrer'] = request.headers.get('REFERER')
        # kw will be urlencoded, need to utf8-encode
        for k, v in kw.items():
            kw[k] = h.really_unicode(v).encode('utf8')
        res = self.service.comment_check(text, data=kw, build_data=False)
        log.info("spam=%s (akismet): %s" % (str(res), log_msg))
        return res
