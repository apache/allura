import mimetypes
import logging

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
