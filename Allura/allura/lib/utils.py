import mimetypes
import logging
from logging.handlers import WatchedFileHandler

import tg
from pylons import response
from paste.httpheaders import CACHE_CONTROL, EXPIRES
from ming.utils import LazyProperty

def cache_forever():
    headers = [
        (k,v) for k,v in response.headers.items()
        if k.lower() not in ('pragma', 'cache-control') ]
    delta = CACHE_CONTROL.apply(
        headers,
        public=True,
        max_age=60*60*24*365)
    EXPIRES.update(headers, delta=delta)
    response.headers.pop('cache-control', None)
    response.headers.pop('pragma', None)
    response.headers.update(headers)

def guess_mime_type(filename):
    '''Guess MIME type based on filename.
    Applies heuristics, tweaks, and defaults in centralized manner.
    '''
    # Consider changing to strict=False
    content_type = mimetypes.guess_type(filename, strict=True)
    if content_type[0]:
        content_type = content_type[0]
    else:
        content_type = 'application/octet-stream'
    return content_type

class ConfigProxy(object):

    def __init__(self, **kw):
        self._kw = kw

    def __getattr__(self, k):
        return tg.config[self._kw[k]]

class lazy_logger(object):
    '''Lazy instatiation of a logger, to ensure that it does not get
    created before logging is configured (which would make it disabled)'''

    def __init__(self, name):
        self._name = name

    @LazyProperty
    def _logger(self):
        return logging.getLogger(self._name)

    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError, name
        return getattr(self._logger, name)

class StatsHandler(WatchedFileHandler):
    fields=('action', 'action_type', 'tool_type', 'tool_mount', 'project', 'neighborhood',
            'username', 'url', 'ip_address')

    def __init__(self,
                 strftime_pattern,
                 module='allura',
                 page=1,
                 **kwargs):
        self.page = page
        self.module = module
        WatchedFileHandler.__init__(self, strftime_pattern)

    def emit(self, record):
        if not hasattr(record, 'action'):
            return
        kwpairs = dict(
            module=self.module,
            page=self.page)
        for name in self.fields:
            kwpairs[name] = getattr(record, name, None)
        kwpairs.update(getattr(record, 'kwpairs', {}))
        record.kwpairs = ','.join(
            '%s=%s' % (k,v) for k,v in sorted(kwpairs.iteritems())
            if v is not None)
        record.exc_info = None # Never put tracebacks in the rtstats log
        WatchedFileHandler.emit(self, record)
    
