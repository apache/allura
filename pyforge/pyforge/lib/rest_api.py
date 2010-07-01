import hmac
import json
import hashlib
import urllib
import urllib2
from urlparse import urljoin
from datetime import datetime

from tg.controllers.util import smart_str
from formencode import variabledecode

class RestClient(object):

    def __init__(self, api_key, secret_key, base_uri,
                 http_username=None, http_password=None):
        self._api_key = api_key
        self._secret_key = secret_key
        self.base_uri = base_uri
        if http_username:
            pw_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
            pw_mgr.add_password(None, base_uri, http_username, http_password)
            auth_handler = urllib2.HTTPBasicAuthHandler(pw_mgr)
            self._opener = urllib2.build_opener(auth_handler)
        else:
            self._opener = urllib2.build_opener()

    def sign_request(self, path, params):
        if hasattr(params, 'items'): params = params.items()
        has_api_key = has_api_timestamp = has_api_signature = False
        for k,v in params:
            if k == 'api_key': has_api_key = True
            if k == 'api_timestamp': has_api_timestamp = True
            if k == 'api_signature': has_api_signature = True
        if not has_api_key: params.append(('api_key', self._api_key))
        if not has_api_timestamp:
            params.append(('api_timestamp', datetime.utcnow().isoformat()))
        if not has_api_signature:
            string_to_sign = path + '?' + urlencode(sorted(params))
            digest = hmac.new(self._secret_key, string_to_sign, hashlib.sha256)
            params.append(('api_signature', digest.hexdigest()))
        return params

    def request(self, method, path, **params):
        req = Request(self, method, path, **params)
        fp = self._opener.open(req)
        return json.loads(fp.read())

class Request(urllib2.Request):

    def __init__(self, client, method, path, **params):
        params = variabledecode.variable_encode(params, add_repetitions=False)
        params = client.sign_request(path, params)
        self._method = method.upper()
        urllib2.Request.__init__(
            self, 
            urljoin(client.base_uri, path),
            data=urlencode(params))

    def get_method(self):
        return self._method

def generate_smart_str(params):
    if isinstance(params, dict): iterparams = params.iteritems()
    else: iterparams = iter(params)
    for key, value in iterparams:
        if value is None: continue
        if isinstance(value, (list, tuple)):
            for item in value:
                yield smart_str(key), smart_str(item)
        else:
            yield smart_str(key), smart_str(value)

def urlencode(params):
    """
    A version of Python's urllib.urlencode() function that can operate on
    unicode strings. The parameters are first case to UTF-8 encoded strings and
    then encoded as per normal.
    """
    return urllib.urlencode([i for i in generate_smart_str(params)])
