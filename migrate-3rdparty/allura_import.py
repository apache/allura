import sys
import urllib
import urllib2
import urlparse
import hmac
import hashlib
from optparse import OptionParser
from pprint import pprint
from datetime import datetime


def parse_options():
    optparser = OptionParser(usage='''%prog [options] <JSON dump>

Import project data dump in JSON format into an Allura project.''')
    optparser.add_option('-a', '--api-key', dest='api_key', help='API key')
    optparser.add_option('-s', '--secret-key', dest='secret_key', help='Secret key')
    optparser.add_option('-p', '--project', dest='project', help='Project to import to')
    optparser.add_option('-t', '--tracker', dest='tracker', help='Tracker to import to')
    optparser.add_option('-u', '--base-url', dest='base_url', default='https://sourceforge.net', help='Base Allura URL (%default)')
    optparser.add_option('--validate', dest='validate', action='store_true', help='Validate import data')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments")
    if not options.api_key or not options.secret_key:
        optparser.error("Keys are required")
    if not options.project or not options.tracker:
        optparser.error("Target project and tracker are required")
    return options, args


class AlluraRestClient(object):

    def __init__(self, base_url, api_key, secret_key):
        self.base_url = base_url
        self.api_key = api_key
        self.secret_key = secret_key
        
    def sign(self, path, params):
        params.append(('api_key', self.api_key))
        params.append(('api_timestamp', datetime.utcnow().isoformat()))
        message = path + '?' + urllib.urlencode(sorted(params))
        digest = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        params.append(('api_signature', digest))
        return params

    def call(self, url, **params):
        url = urlparse.urljoin(options.base_url, url)
        params = self.sign(urlparse.urlparse(url).path, params.items())

        try:
            result = urllib2.urlopen(url, urllib.urlencode(params))
            return result.read()
        except urllib2.HTTPError, e:
            if options.verbose:
                error_content = e.read()
                e.msg += '. Error response:\n' + error_content
            raise e

    
if __name__ == '__main__':
    options, args = parse_options()
    url = '/rest/p/' + options.project + '/' + options.tracker
    if options.validate:
        url += '/validate_import'
    else:
        url += '/perform_import'

    cli = AlluraRestClient(options.base_url, options.api_key, options.secret_key)
    print cli.call(url, doc=open(args[0]).read())
