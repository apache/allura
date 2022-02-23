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

from tg import request
from tg import tmpl_context as c

from allura.lib import helpers as h
from allura.lib import utils
from allura.lib.spam import SpamFilter

try:
    import akismet
    AKISMET_AVAILABLE = True
except ImportError:
    AKISMET_AVAILABLE = False


log = logging.getLogger(__name__)


if AKISMET_AVAILABLE:
    class AkismetWithoutStartupVerify(akismet.Akismet):
        def __init__(self, key=None, blog_url=None):
            # avoid possible errors at instantiation time, will encounter them later
            self.api_key = key
            self.blog_url = blog_url


class AkismetSpamFilter(SpamFilter):

    """Spam checking implementation via Akismet service.

    To enable Akismet spam filtering in your Allura instance, first pip install akismet (see requirements-optional.txt)
    and then include the following parameters in your .ini file::

        spam.method = akismet
        spam.key = <your Akismet key here>
    """

    def __init__(self, config):
        if not AKISMET_AVAILABLE:
            raise ImportError('akismet not available')
        self.service = AkismetWithoutStartupVerify(config['spam.key'], config['base_url'])

    def get_data(self, text, artifact=None, user=None, content_type='comment', request=None, **kw):
        # Docs: https://akismet.com/development/api/
        kw['comment_content'] = text
        kw['comment_type'] = content_type
        if artifact:
            try:
                # if its a comment, get wiki, ticket, etc URL
                url = artifact.main_url()
            except Exception:
                url = artifact.url()
            kw['permalink'] = h.absurl(url)
            if hasattr(artifact, 'timestamp'):
                # Message & Post objects
                date_created = artifact.timestamp
            else:
                # fallback for other artifacts, not exactly "created" date though
                date_created = artifact.mod_date
            kw['comment_date_gmt'] = date_created.isoformat()
            kw['comment_post_modified_gmt'] = artifact.primary().mod_date.isoformat()
        user = user or c.user
        if user:
            kw['comment_author'] = user.display_name or user.username
            kw['comment_author_email'] = user.email_addresses[0] if user.email_addresses else ''
        if request is not None:
            kw['user_ip'] = utils.ip_address(request)
            kw['user_agent'] = request.headers.get('USER_AGENT')
            kw['referrer'] = request.headers.get('REFERER')
        else:
            # these are required fields, but for ham/spam reports we don't have the original values to send :/
            kw['user_ip'] = None
            kw['user_agent'] = None
            if artifact and hasattr(artifact, 'get_version'):  # VersionedArtifacts (includes comment posts)
                try:
                    kw['user_ip'] = artifact.get_version(1).author.logged_ip
                except IndexError:
                    log.debug("couldn't get Snapshot for this artifact %s", artifact)

        # kw will be urlencoded, need to utf8-encode
        for k, v in kw.items():
            kw[k] = h.really_unicode(v).encode('utf8')
        return kw

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        res = self.service.comment_check(**self.get_data(text=text,
                                                         artifact=artifact,
                                                         user=user,
                                                         content_type=content_type,
                                                         request=request,
                                                         ))
        self.record_result(res, artifact, user)
        return res

    def submit_spam(self, text, artifact=None, user=None, content_type='comment'):
        self.service.submit_spam(**self.get_data(text=text,
                                                 artifact=artifact,
                                                 user=user,
                                                 content_type=content_type))

    def submit_ham(self, text, artifact=None, user=None, content_type='comment'):
        self.service.submit_ham(**self.get_data(text=text,
                                                artifact=artifact,
                                                user=user,
                                                content_type=content_type))
