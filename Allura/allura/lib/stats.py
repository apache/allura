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

from __future__ import with_statement
from time import time
from contextlib import contextmanager
from pylons import request


class StatsRecord(object):

    def __init__(self, request, active):
        self.timers = dict(
            mongo=0,
            template=0,
            total=0)
        self.url = request.environ['PATH_INFO']
        self.active = active
        # Avoid double-timing things
        self._now_timing = set()

    def __repr__(self):
        stats = ' '.join(
            ('%s=%.0fms' % (k, v * 1000))
            for k, v in sorted(self.timers.iteritems()))
        return '%s: %s' % (self.url, stats)

    def asdict(self):
        return dict(
            url=self.url,
            timers=self.timers)

    @contextmanager
    def timing(self, name):
        if self.active and name not in self._now_timing:
            self._now_timing.add(name)
            self.timers.setdefault(name, 0)
            begin = time()
            try:
                yield
            finally:
                end = time()
                self.timers[name] += end - begin
                self._now_timing.remove(name)
        else:
            yield


class timing(object):

    '''Decorator to time a method call'''

    def __init__(self, timer):
        self.timer = timer

    def __call__(self, func):
        def inner(*l, **kw):
            try:
                stats = request.environ['sf.stats']
            except TypeError:
                return func(*l, **kw)
            with stats.timing(self.timer):
                return func(*l, **kw)
        inner.__name__ = func.__name__
        return inner

    def decorate(self, obj, names):
        names = names.split()
        for name in names:
            setattr(obj, name,
                    self(getattr(obj, name)))
