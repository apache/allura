import sys
import urllib2
from optparse import OptionParser
from pprint import pprint

from allura.lib import rest_api


def parse_options():
    optparser = OptionParser(usage=''' %prog --api-key= --secret-key= <JSON dump>

Import project data dump in JSON format into Allura project.''')
    optparser.add_option('-a', '--api-key', dest='api_key', help='API key')
    optparser.add_option('-s', '--secret-key', dest='secret_key', help='Secret key')
    optparser.add_option('-u', '--base-url', dest='base_url', default='https://sourceforge.net', help='Base Allura URL (%default)')
    optparser.add_option('--validate', dest='validate', action='store_true', help='Validate import data')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments.")
    if not options.api_key or not options.secret_key:
        optparser.error("Keys are required.")
    return options, args


class RestClient(rest_api.RestClient):

    def call(self, method, url, **params):
        try:
            return self.request(method, url, **params)
        except urllib2.HTTPError, e:
            error_content = e.fp.read()
            e.msg += '. Error response:\n' + error_content
            raise e

    
if __name__ == '__main__':
    options, args = parse_options()
    if options.validate:
        url = '/rest/p/test/bugs/validate_import'
    else:
        url = '/rest/p/test/bugs/perform_import'

    cli = RestClient(base_uri=options.base_url, api_key=options.api_key, secret_key=options.secret_key)
    print cli.call('POST', url, doc=open(args[0]).read())
