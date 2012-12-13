import logging

from pylons import request
from pylons import tmpl_context as c

import akismet

log = logging.getLogger(__name__)

class Akismet(akismet.Akismet):
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
        res = self.comment_check(text, data=kw, build_data=False)
        log.info("spam=%s (akismet): %s" % (str(res), log_msg))
        return res
