import sys
import urllib
import urllib2
import urlparse
import hmac
import hashlib
import json
from optparse import OptionParser
from pprint import pprint
from datetime import datetime

from allura_api import AlluraApiClient


def parse_options():
    optparser = OptionParser(usage='''%prog [options] <JSON dump>

Import project data dump in JSON format into an Allura project.''')
    optparser.add_option('-a', '--api-ticket', dest='api_key', help='API ticket')
    optparser.add_option('-s', '--secret-key', dest='secret_key', help='Secret key')
    optparser.add_option('-p', '--project', dest='project', help='Project to import to')
    optparser.add_option('-t', '--tracker', dest='tracker', help='Tracker to import to')
    optparser.add_option('-u', '--base-url', dest='base_url', default='https://sourceforge.net', help='Base Allura URL (%default)')
    optparser.add_option('-o', dest='import_opts', default=[], action='append', help='Specify import option(s)', metavar='opt=val')
    optparser.add_option('--user-map', dest='user_map_file', help='Map original users to SF.net users', metavar='JSON_FILE')
    optparser.add_option('--validate', dest='validate', action='store_true', help='Validate import data')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments")
    if not options.api_key or not options.secret_key:
        optparser.error("Keys are required")
    if not options.project or not options.tracker:
        optparser.error("Target project and tracker are required")
    return optparser, options, args


if __name__ == '__main__':
    optparser, options, args = parse_options()

    import_options = {}
    for s in options.import_opts:
        k, v = s.split('=', 1)
        if v == 'false':
            v = False
        import_options[k] = v

    user_map = {}
    if options.user_map_file:
        f = open(options.user_map_file)
        try:
            user_map = json.load(f)
            if type(user_map) is not type({}):
                raise ValueError
            for k, v in user_map.iteritems():
                print k, v
                if not isinstance(k, basestring) or not isinstance(v, basestring):
                    raise ValueError
        except ValueError:
            optparser.error('--user-map should specify JSON file with format {"original_user": "sf_user", ...}')
        finally:
            f.close()

    import_options['user_map'] = user_map

    cli = AlluraApiClient(options.base_url, options.api_key, options.secret_key, options.verbose)
    url = '/rest/p/' + options.project + '/' + options.tracker
    doc_txt = open(args[0]).read()
    if options.validate:
        url += '/validate_import'
        print cli.call(url, doc=doc_txt, options=json.dumps(import_options))
    else:
        url += '/perform_import'

        doc = json.loads(doc_txt)
        tickets_in = doc['trackers']['default']['artifacts']
        doc['trackers']['default']['artifacts'] = []
        if options.verbose:
            print "Importing %d tickets" % len(tickets_in)

        cnt = 0
        for ticket_in in tickets_in:
            cnt += 1
            doc['trackers']['default']['artifacts'] = [ticket_in]
            res = cli.call(url, doc=json.dumps(doc), options=json.dumps(import_options))
            assert res['status'] and not res['errors']
            if res['warnings']:
                print "Imported ticket id %s, warnings: %s" % (ticket_in['id'], res['warnings'])
            else:
                print "Imported ticket id %s" % (ticket_in['id'])
