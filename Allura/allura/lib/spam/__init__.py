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
from copy import copy

from paste.deploy.converters import aslist

from allura.lib.helpers import exceptionless
from allura.model.artifact import SpamCheckResult

log = logging.getLogger(__name__)


class SpamFilter:

    """Defines the spam checker interface and provides a default no-op impl."""

    def __init__(self, config):
        pass

    @property
    def filter_name(self):
        return self.__class__.__name__.replace('SpamFilter', '').lower()

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        """Return True if ``text`` is spam, else False."""
        log.info("No spam checking enabled")
        return False

    def submit_spam(self, text, artifact=None, user=None, content_type='comment', **kw):
        log.info("No submit_spam available for %s", self.filter_name)

    def submit_ham(self, text, artifact=None, user=None, content_type='comment', **kw):
        log.info("No submit_ham available for %s", self.filter_name)

    def record_result(self, result, artifact, user):
        log.info("spam={} ({}): {}".format(str(result), self.filter_name, artifact.url() if artifact else ''))
        r = SpamCheckResult(
            ref=artifact.ref if artifact else None,
            project_id=artifact.project_id if artifact else None,
            user=user,
            result=result,
        )

    @classmethod
    def get(cls, config, entry_points):
        """
        Return an instance of the SpamFilter impl specified in ``config``.
        :rtype: SpamFilter
        """
        method = config.get('spam.method')
        if not method:
            return cls(config)
        elif ' ' in method:
            return ChainedSpamFilter(method, entry_points, config)
        else:
            result = entry_points[method]
            filter_obj = result(config)
            filter_obj.check = exceptionless(False, log=log)(filter_obj.check)
            return filter_obj


class ChainedSpamFilter(SpamFilter):

    def __init__(self, methods_string, entry_points, config):
        methods = aslist(methods_string)
        self.filters = []
        for m in methods:
            config = dict(config).copy()
            config['spam.method'] = m
            spam_filter = SpamFilter.get(config=config, entry_points=entry_points)
            self.filters.append(spam_filter)

    def check(self, *a, **kw):
        for spam_filter in self.filters:
            # note: SpamFilter.get() has wrapped all .check() functions with exceptionless
            if spam_filter.check(*a, **kw):
                return True
        return False

    def submit_spam(self, *a, **kw):
        for spam_filter in self.filters:
            spam_filter.submit_spam(*a, **kw)

    def submit_ham(self, *a, **kw):
        for spam_filter in self.filters:
            spam_filter.submit_ham(*a, **kw)
