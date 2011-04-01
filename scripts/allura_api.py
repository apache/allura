import sys
import urllib
import urllib2
import urlparse
import hmac
import hashlib
import json
from datetime import datetime


class AlluraApiClient(object):

    def __init__(self, base_url, api_key, secret_key, verbose=False):
        self.base_url = base_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.verbose = verbose

    def sign(self, path, params):
        params.append(('api_key', self.api_key))
        params.append(('api_timestamp', datetime.utcnow().isoformat()))
        message = path + '?' + urllib.urlencode(sorted(params))
        digest = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        params.append(('api_signature', digest))
        return params

    def call(self, url, **params):
        url = urlparse.urljoin(self.base_url, url)
        params = self.sign(urlparse.urlparse(url).path, params.items())

        try:
            result = urllib2.urlopen(url, urllib.urlencode(params))
            resp = result.read()
            return json.loads(resp)
        except urllib2.HTTPError, e:
            if self.verbose:
                error_content = e.read()
                e.msg += '. Error response:\n' + error_content
            raise e
