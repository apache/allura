#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


import argparse
import json
import logging

from allura.scripts import ScriptTask
from allura.lib.import_api import AlluraImportApiClient

log = logging.getLogger(__name__)

def import_tracker(cli, project, tool, import_options, doc_txt,
        validate=True, verbose=False, cont=False):
    url = '/rest/p/' + project + '/' + tool
    if validate:
        url += '/validate_import'
    else:
        url += '/perform_import'

    existing_map = {}
    if cont:
        existing_tickets = cli.call('/rest/p/' + project + '/' + tool + '/')['tickets']
        for t in existing_tickets:
            existing_map[t['ticket_num']] = t['summary']

    doc = json.loads(doc_txt)

    if 'trackers' in doc and 'default' in doc['trackers'] and 'artifacts' in doc['trackers']['default']:
        tickets_in = doc['trackers']['default']['artifacts']
        doc['trackers']['default']['artifacts'] = []
    else:
        tickets_in = doc

    if verbose:
        print "Processing %d tickets" % len(tickets_in)

    for cnt, ticket_in in enumerate(tickets_in):
        if ticket_in['id'] in existing_map:
            if verbose:
                print 'Ticket id %d already exists, skipping' % ticket_in['id']
            continue
        doc_import={}
        doc_import['trackers'] = {}
        doc_import['trackers']['default'] = {}
        doc_import['trackers']['default']['artifacts'] = [ticket_in]
        res = cli.call(url, doc=json.dumps(doc_import), options=json.dumps(import_options))
        assert res['status'] and not res['errors']
        if validate:
            if res['warnings']:
                print "Ticket id %s warnings: %s" % (ticket_in['id'], res['warnings'])
        else:
            print "Imported ticket id %s" % (ticket_in['id'])

class ImportTracker(ScriptTask):
    @classmethod
    def execute(cls, options):
        user_map = {}
        import_options = {}
        for s in options.import_opts:
            k, v = s.split('=', 1)
            if v == 'false':
                v = False
            import_options[k] = v

        if options.user_map_file:
            f = open(options.user_map_file)
            try:
                user_map = json.load(f)
                if type(user_map) is not type({}):
                    raise ValueError
                for k, v in user_map.iteritems():
                    if not isinstance(k, basestring) or not isinstance(v, basestring):
                        raise ValueError
            except ValueError:
                raise '--user-map should specify JSON file with format {"original_user": "sf_user", ...}'
            finally:
                f.close()
        import_options['user_map'] = user_map
        cli = AlluraImportApiClient(options.base_url, options.api_key, options.secret_key, options.verbose)
        doc_txt = open(options.file_data).read()
        import_tracker(cli, options.project, options.tracker, import_options, doc_txt,
                       validate=options.validate,
                       verbose=options.verbose,
                       cont=options.cont)

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='import tickets from json')
        parser.add_argument('--nbhd', action='store', default='', dest='nbhd',
                help='Restrict update to a particular neighborhood, e.g. /p/.')
        parser.add_argument('-a', '--api-ticket', action='store', dest='api_key', help='API ticket')
        parser.add_argument('-s', '--secret-key', action='store', dest='secret_key', help='Secret key')
        parser.add_argument('-p', '--project', action='store', dest='project', help='Project to import to')
        parser.add_argument('-t', '--tracker', action='store', dest='tracker', help='Tracker to import to')
        parser.add_argument('-u', '--base-url', dest='base_url', default='https://sourceforge.net', help='Base Allura URL (https://sourceforge.net)')
        parser.add_argument('-o', dest='import_opts', default=[], action='store',  help='Specify import option(s)', metavar='opt=val')
        parser.add_argument('--user-map', dest='user_map_file', help='Map original users to SF.net users', metavar='JSON_FILE')
        parser.add_argument('--file_data', dest='file_data', help='json file', metavar='JSON_FILE')
        parser.add_argument('--validate', dest='validate', action='store_true', help='Validate import data')
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
        parser.add_argument('-c', '--continue', dest='cont', action='store_true', help='Continue import into existing tracker')
        return parser


if __name__ == '__main__':
    ImportTracker.main()
