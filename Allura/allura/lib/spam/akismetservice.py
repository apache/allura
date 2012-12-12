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
        kw['user_ip'] = request.environ['HTTP_X_REMOTE_ADDR']
        kw['user_agent'] = request.environ['HTTP_USER_AGENT']
        kw['referrer'] = request.environ['HTTP_REFERER']
        res = self.comment_check(text, data=kw, build_data=False)
        log.info("spam=%s (akismet): %s" % (str(res), log_msg))
        return res
