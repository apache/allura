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
    import Mollom
    MOLLOM_AVAILABLE = True
except ImportError:
    MOLLOM_AVAILABLE = False


log = logging.getLogger(__name__)


class MollomSpamFilter(SpamFilter):

    """Spam checking implementation via Mollom service.

    To enable Mollom spam filtering in your Allura instance, first
    enable the entry point in setup.py::

        [allura.spam]
        mollom = allura.lib.spam.mollomfilter:MollomSpamFilter

    Then include the following parameters in your .ini file::

        spam.method = mollom
        spam.public_key = <your Mollom public key here>
        spam.private_key = <your Mollom private key here>
    """

    def __init__(self, config):
        if not MOLLOM_AVAILABLE:
            raise ImportError('Mollom not available')
        self.service = Mollom.MollomAPI(
            publicKey=config.get('spam.public_key'),
            privateKey=config.get('spam.private_key'))
        if not self.service.verifyKey():
            raise Mollom.MollomFault('Your MOLLOM credentials are invalid.')

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        """Basic content spam check via Mollom. For more options
        see http://mollom.com/api#api-content
        """
        log_msg = text
        kw['postBody'] = text
        if artifact:
            try:
                # if its a comment, get wiki, ticket, etc URL
                url = artifact.main_url()
            except:
                url = artifact.url()
            # Should be able to send url, but can't right now due to a bug in
            # the PyMollom lib
            # kw['url'] = url
            log_msg = url
        user = user or c.user
        if user:
            kw['authorName'] = user.display_name or user.username
            kw['authorMail'] = user.email_addresses[
                0] if user.email_addresses else ''
        kw['authorIP'] = utils.ip_address(request)
        # kw will be urlencoded, need to utf8-encode
        for k, v in kw.items():
            kw[k] = h.really_unicode(v).encode('utf8')
        cc = self.service.checkContent(**kw)
        res = cc['spam'] == 2
        artifact.spam_check_id = cc.get('session_id', '')
        log.info("spam=%s (mollom): %s" % (str(res), log_msg))
        return res

    def submit_spam(self, text, artifact=None, user=None, content_type='comment', **kw):
        self.service.sendFeedback(artifact.spam_check_id, 'spam')

    def submit_ham(self, *args, **kw):
        log.info("Mollom doesn't support reporting a ham")
