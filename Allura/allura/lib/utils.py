import mimetypes

from pylons import response
from paste.httpheaders import CACHE_CONTROL, EXPIRES

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
