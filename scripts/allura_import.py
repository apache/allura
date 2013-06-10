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

import json
from optparse import OptionParser
from datetime import datetime

from allura.lib.import_api import AlluraImportApiClient
from forgetracker.scripts.import_tracker import import_tracker


def main():
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

    cli = AlluraImportApiClient(options.base_url, options.api_key, options.secret_key, options.verbose)
    doc_txt = open(args[0]).read()

    # import the tracker (if any)
    if options.tracker:
        import_tracker(cli, options.project, options.tracker, import_options, options, doc_txt,
                       validate=options.validate,
                       verbose=options.verbose)
    elif options.forum:
        import_forum(cli, options.project, options.forum, user_map, doc_txt, validate=options.validate)


def import_forum(cli, project, tool, user_map, doc_txt, validate=True):
    url = '/rest/p/' + project + '/' + tool
    if validate:
        url += '/validate_import'
        print cli.call(url, doc=doc_txt, user_map=json.dumps(user_map))
    else:
        url += '/perform_import'
        print cli.call(url, doc=doc_txt, user_map=json.dumps(user_map))


def parse_options():
    optparser = OptionParser(usage='''%prog [options] <JSON dump>

Import project data dump in JSON format into an Allura project.''')
    optparser.add_option('-a', '--api-ticket', dest='api_key', help='API ticket')
    optparser.add_option('-s', '--secret-key', dest='secret_key', help='Secret key')
    optparser.add_option('-p', '--project', dest='project', help='Project to import to')
    optparser.add_option('-t', '--tracker', dest='tracker', help='Tracker to import to')
    optparser.add_option('-f', '--forum', dest='forum', help='Forum tool to import to')
    optparser.add_option('-u', '--base-url', dest='base_url', default='https://sourceforge.net', help='Base Allura URL (%default)')
    optparser.add_option('-o', dest='import_opts', default=[], action='append', help='Specify import option(s)', metavar='opt=val')
    optparser.add_option('--user-map', dest='user_map_file', help='Map original users to SF.net users', metavar='JSON_FILE')
    optparser.add_option('--validate', dest='validate', action='store_true', help='Validate import data')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
    optparser.add_option('-c', '--continue', dest='cont', action='store_true', help='Continue import into existing tracker')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments")
    if not options.api_key or not options.secret_key:
        optparser.error("Keys are required")
    if not options.project:
        optparser.error("Target project is required")
    return optparser, options, args


if __name__ == '__main__':
    main()

