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

from allura.lib.import_api import AlluraImportApiClient
from tracwikiimporter.scripts.wiki_from_trac.loaders import import_wiki
import six


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
            if not isinstance(user_map, type({})):
                raise ValueError
            for k, v in user_map.items():
                print(k, v)
                if not isinstance(k, str) or not isinstance(v, str):
                    raise ValueError
        except ValueError:
            optparser.error(
                '--user-map should specify JSON file with format {"original_user": "sf_user", ...}')
        finally:
            f.close()

    import_options['user_map'] = user_map

    cli = AlluraImportApiClient(options.base_url, options.token, options.verbose)
    doc_txt = open(args[0]).read()

    if options.forum:
        import_forum(cli, options.project, options.forum, user_map, doc_txt,
                     validate=options.validate, neighborhood=options.neighborhood)
    elif options.wiki:
        import_wiki(cli, options.project, options.wiki, options, doc_txt)



def import_forum(cli, project, tool, user_map, doc_txt, validate=True,
        neighborhood='p'):
    url = '/rest/{neighborhood}/{project}/{tool}'.format(
            neighborhood=neighborhood,
            project=project,
            tool=tool,
            )
    if validate:
        url += '/validate_import'
        print(cli.call(url, doc=doc_txt, user_map=json.dumps(user_map)))
    else:
        url += '/perform_import'
        print(cli.call(url, doc=doc_txt, user_map=json.dumps(user_map)))


def parse_options():
    optparser = OptionParser(usage='''%prog [options] <JSON dump>

Import project data dump in JSON format into an Allura project.''')
    optparser.add_option('-t', '--token', dest='token',
                         help='OAuth bearer token (generate at /auth/oauth/)')
    optparser.add_option('-p', '--project', dest='project',
                         help='Project to import to')
    optparser.add_option('-n', '--neighborhood', dest='neighborhood',
                         help="URL prefix of destination neighborhood (default is 'p')",
                         default='p')
    optparser.add_option('-f', '--forum', dest='forum',
                         help='Forum tool to import to')
    optparser.add_option('-w', '--wiki', dest='wiki',
                         help='Wiki tool to import to')
    optparser.add_option('-u', '--base-url', dest='base_url',
                         default='https://sourceforge.net', help='Base Allura URL (%default)')
    optparser.add_option('-o', dest='import_opts',
                         default=[], action='append', help='Specify import option(s)', metavar='opt=val')
    optparser.add_option('--user-map', dest='user_map_file',
                         help='Map original users to SF.net users', metavar='JSON_FILE')
    optparser.add_option('--validate', dest='validate',
                         action='store_true', help='Validate import data')
    optparser.add_option('-v', '--verbose', dest='verbose',
                         action='store_true', help='Verbose operation')
    optparser.add_option('-c', '--continue', dest='cont',
                         action='store_true', help='Continue import into existing tracker')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments")
    if not options.token:
        optparser.error("OAuth bearer token is required")
    if not options.project:
        optparser.error("Target project is required")
    options.neighborhood = options.neighborhood.strip('/')
    return optparser, options, args


if __name__ == '__main__':
    main()
