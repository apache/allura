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

import logging

from pylons import request
from pylons import tmpl_context as c

from allura.lib import helpers as h
from allura.lib import utils
from allura.lib.spam import SpamFilter

try:
    import akismet
    AKISMET_AVAILABLE = True
except ImportError:
    AKISMET_AVAILABLE = False


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
        if not AKISMET_AVAILABLE:
            raise ImportError('akismet not available')
        self.service = akismet.Akismet(
            config.get('spam.key'), config.get('base_url'))
        self.service.verify_key()

    def get_data(self, text, artifact=None, user=None, content_type='comment', request=None, **kw):
        kw['comment_content'] = text
        kw['comment_type'] = content_type
        if artifact:
            try:
                # if its a comment, get wiki, ticket, etc URL
                url = artifact.main_url()
            except:
                url = artifact.url()
            kw['permalink'] = url
        user = user or c.user
        if user:
            kw['comment_author'] = user.display_name or user.username
            kw['comment_author_email'] = user.email_addresses[0] if user.email_addresses else ''
        if request:
            kw['user_ip'] = utils.ip_address(request)
            kw['user_agent'] = request.headers.get('USER_AGENT')
            kw['referrer'] = request.headers.get('REFERER')
        # kw will be urlencoded, need to utf8-encode
        for k, v in kw.items():
            kw[k] = h.really_unicode(v).encode('utf8')
        return kw

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        res = self.service.comment_check(text,
                                         data=self.get_data(text=text,
                                                            artifact=artifact,
                                                            user=user,
                                                            content_type=content_type,
                                                            request=request,
                                                            ),
                                         build_data=False)
        log.info("spam=%s (akismet): %s" % (str(res), artifact.url() if artifact else text))
        return res

    def submit_spam(self, text, artifact=None, user=None, content_type='comment'):
        self.service.submit_spam(text,
                                 data=self.get_data(text=text,
                                                    artifact=artifact,
                                                    user=user,
                                                    content_type=content_type),
                                 build_data=False)

    def submit_ham(self, text, artifact=None, user=None, content_type='comment'):
        self.service.submit_ham(text,
                                data=self.get_data(text=text,
                                                   artifact=artifact,
                                                   user=user,
                                                   content_type=content_type),
                                build_data=False)
