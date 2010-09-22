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
