import sys
import json
from optparse import OptionParser
from pprint import pprint
from datetime import datetime
import logging

from allura_import_api import AlluraImportApiClient


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


def time_normalize(t):
    return t.replace('T', ' ').replace('Z', '')


def verify_ticket(ticket_in, ticket_out):
    assert ticket_out['summary'] == ticket_in['summary']
    assert ticket_out['description'] == ticket_in['description']
    assert ticket_out['created_date'] == time_normalize(ticket_in['date'])
    assert ticket_out['status'] == ticket_in['status']
    for key in ('cc', 'private', 'resolution', 'milestone', 'component', 'version', 'type', 'severity', 'priority'):
        if key in ticket_in:
            assert ticket_out['custom_fields']['_' + key] == ticket_in[key]

def run_test(file_name, base_url, api_ticket, secret_key, project, tracker, limit=None, verbose=False):
    import_options = {}
    user_map = {}
    import_options['user_map'] = user_map
    url = '/rest/p/' + project + '/' + tracker + '/perform_import'

    cli = AlluraImportApiClient(base_url, api_ticket, secret_key, verbose)
    existing_tickets = cli.call('/rest/p/' + project + '/' + tracker + '/')['tickets']
    if len(existing_tickets) > 0:
        print "Warning: importing into non-empty tracker, some checks below may be bogus"

    doc_txt = open(file_name).read()
    doc = json.loads(doc_txt)
    tickets_in = doc['trackers']['default']['artifacts']
    doc['trackers']['default']['artifacts'] = []
    if not limit:
        limit = len(tickets_in)
    print "Importing %d tickets" % limit

    errors = []
    for cnt, ticket_in in enumerate(tickets_in, start=1):
        if cnt > limit:
            break
        doc['trackers']['default']['artifacts'] = [ticket_in]
        res = cli.call(url, doc=json.dumps(doc), options=json.dumps(import_options))
        print "Imported ticket id %s (%d of %d), result: %s" % (ticket_in['id'], cnt, limit, res)
        if not res['status'] or res['errors']:
            errors.append((ticket_in['id'], res))
            print "Error import ticket %d: %s" % (ticket_in['id'], res)
            continue

        ticket_out = cli.call('/rest/p/' + project + '/' + tracker + '/' + str(ticket_in['id']) + '/')
        ticket_out = ticket_out['ticket']
        verify_ticket(ticket_in, ticket_out)
        print "Verified ticket"

    print "Import complete, counting tickets in tracker"
    tickets_out = cli.call('/rest/p/' + project + '/' + tracker + '/')['tickets']
    print "Fetched back ticket list of size:", len(tickets_out)
    assert len(tickets_out) - len(existing_tickets) == limit
    return errors


if __name__ == '__main__':
    logging.basicConfig()
    optparser, options, args = parse_options()

    errors = run_test(args[0], options.base_url, options.api_key, options.secret_key,
                      options.project, options.tracker, options.verbose)

    if errors:
        print "There were %d errors during import:" % len(errors)
        for e in errors:
            print e
