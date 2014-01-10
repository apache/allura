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

from allura.lib.helpers import exceptionless

log = logging.getLogger(__name__)


class SpamFilter(object):

    """Defines the spam checker interface and provides a default no-op impl."""

    def __init__(self, config):
        pass

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        """Return True if ``text`` is spam, else False."""
        log.info("No spam checking enabled")
        return False

    def submit_spam(self, text, artifact=None, user=None, content_type='comment', **kw):
        log.info("No spam checking enabled")

    def submit_ham(self, text, artifact=None, user=None, content_type='comment', **kw):
        log.info("No spam checking enabled")

    @classmethod
    def get(cls, config, entry_points):
        """Return an instance of the SpamFilter impl specified in ``config``.
        """
        method = config.get('spam.method')
        if not method:
            return cls(config)
        result = entry_points[method]
        filter_obj = result(config)
        filter_obj.check = exceptionless(False, log=log)(filter_obj.check)
        return filter_obj
