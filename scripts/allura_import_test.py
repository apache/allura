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


def parse_options():
    optparser = OptionParser(usage='''%prog [options] <JSON dump>

Integration test for tracker import. How to use:
1. In 'test' project, create 'tickets' tracker.
2. Create API ticket for importing into 'test' project.
3. Run %prog -a <api ticket> -s <secret> data/sf.json
''')
    optparser.add_option('-a', '--api-ticket', dest='api_key', help='API ticket')
    optparser.add_option('-s', '--secret-key', dest='secret_key', help='Secret key')
    optparser.add_option('-p', '--project', dest='project', default='test', help='Project to import to (%default)')
    optparser.add_option('-t', '--tracker', dest='tracker', default='tickets', help='Tracker to import to (%default)')
    optparser.add_option('-u', '--base-url', dest='base_url', default='http://localhost:8080', help='Base Allura URL (%default)')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments")
    if not options.api_key or not options.secret_key:
        optparser.error("Keys are required")
    if not options.project or not options.tracker:
        optparser.error("Target project and tracker are required")
    return optparser, options, args


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
            resp = result.read()
            return json.loads(resp)
        except urllib2.HTTPError, e:
            if options.verbose:
                error_content = e.read()
                e.msg += '. Error response:\n' + error_content
            raise e

def time_normalize(t):
    return t.replace('T', ' ').replace('Z', '')

def verify_ticket(ticket_in, ticket_out):
    assert ticket_out['summary'] == ticket_in['summary']
    assert ticket_out['description'] == ticket_in['description']
    assert ticket_out['created_date'] == time_normalize(ticket_in['date'])
    assert ticket_out['status'] == ticket_in['status']
    assert ticket_out['custom_fields']['_cc'] == ticket_in['cc']
    assert ticket_out['custom_fields']['_private'] == ticket_in['private']
    assert ticket_out['custom_fields']['_resolution'] == ticket_in['resolution']


if __name__ == '__main__':
    optparser, options, args = parse_options()
    url = '/rest/p/' + options.project + '/' + options.tracker
    url += '/perform_import'

    import_options = {}

    user_map = {}
    import_options['user_map'] = user_map

    cli = AlluraRestClient(options.base_url, options.api_key, options.secret_key)

    existing_tickets = cli.call('/rest/p/' + options.project + '/' + options.tracker + '/')['tickets']
    if len(existing_tickets) > 0:
        print "Warning: importing into non-empty tracker, some checks below may be bogus"

    doc_txt = open(args[0]).read()
    doc = json.loads(doc_txt)
    tickets_in = doc['trackers']['default']['artifacts']
    doc['trackers']['default']['artifacts'] = []
    print "Importing %d tickets" % len(tickets_in)

    cnt = 0
    for ticket_in in tickets_in:
        cnt += 1
        doc['trackers']['default']['artifacts'] = [ticket_in]
        res = cli.call(url, doc=json.dumps(doc), options=json.dumps(import_options))
        print "Imported ticket id %s (%d of %d), result: %s" % (ticket_in['id'], cnt, len(tickets_in), res)
        assert res['status']
        assert not res['errors']

        ticket_out = cli.call('/rest/p/' + options.project + '/' + options.tracker + '/' + str(ticket_in['id']) + '/')
        ticket_out = ticket_out['ticket']
        verify_ticket(ticket_in, ticket_out)
        print "Verified ticket"

    print "Import complete, counting tickets in tracker"
    tickets_out = cli.call('/rest/p/' + options.project + '/' + options.tracker + '/')['tickets']
    print "Fetched back ticket list of size:", len(tickets_out)
    assert len(tickets_out) - len(existing_tickets) == len(tickets_in)
