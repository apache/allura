from __future__ import with_statement
from time import time
from contextlib import contextmanager

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
            ('%s=%.0fms' % (k,v*1000))
            for k,v in sorted(self.timers.iteritems()))
        return '%s: %s' % (self.url, stats)

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
                self.timers[name] += end-begin
                self._now_timing.remove(name)
        else:
            yield

class timing(object):
    '''Decorator to time a method call'''

    def __init__(self, timer):
        self.timer = timer

    def __call__(self, func):
        from allura.lib.custom_middleware import environ
        def inner(*l, **kw):
            try:
                stats = environ['sf.stats']
            except KeyError:
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
