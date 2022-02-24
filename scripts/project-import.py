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
import logging
import sys

from ming.orm import session
import colander

from allura import model as M
from allura.lib.project_create_helpers import create_project_with_attrs, make_newproject_schema, deserialize_project

log = logging.getLogger(__name__)


def main(options):
    root_logger = logging.getLogger()
    root_logger.addHandler(logging.StreamHandler(sys.stdout))
    root_logger.setLevel(getattr(logging, options.log_level.upper()))
    log.debug(options)

    nbhd = M.Neighborhood.query.get(name=options.neighborhood)
    if not nbhd:
        return 'Invalid neighborhood "%s".' % options.neighborhood

    data = json.load(open(options.file))

    projectSchema = make_newproject_schema(nbhd, options.update)
    # allow 'icon' as a local filesystem path via this script only
    projectSchema.add(colander.SchemaNode(colander.Str(), name='icon', missing=None))

    projects = []
    for datum in data:
        try:
            if options.update and not datum.get('shortname'):
                log.warning('Shortname not provided with --update; this will create new projects instead of updating')
            projects.append(deserialize_project(datum, projectSchema, nbhd))
        except Exception:
            keep_going = options.validate_only
            log.error('Error on %s\n%s', datum['shortname'], datum, exc_info=keep_going)
            if not keep_going:
                raise

    log.debug(projects)

    if options.validate_only:
        return

    for p in projects:
        log.info('Creating{} project "{}".'.format('/updating' if options.update else '', p.shortname))
        try:
            project = create_project_with_attrs(p, nbhd, update=options.update, ensure_tools=options.ensure_tools)
        except Exception as e:
            log.exception('%s' % (str(e)))
            project = False
        if not project:
            log.warning('Stopping due to error.')
            return 1
        session(project).clear()

    log.warning('Done.')
    return 0


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(
        description='Import Allura project(s) from JSON file')
    parser.add_argument('file', metavar='JSON_FILE', type=str,
                        help='Path to JSON file containing project data.')
    parser.add_argument('neighborhood', metavar='NEIGHBORHOOD', type=str,
                        help='Neighborhood name like "Projects"')
    parser.add_argument('--log', dest='log_level', default='INFO',
                        help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    parser.add_argument('--update', dest='update', default=False,
                        action='store_true',
                        help='Update existing projects. Without this option, existing '
                        'projects will be skipped.')
    parser.add_argument('--ensure-tools', dest='ensure_tools', default=False,
                        action='store_true',
                        help='Check nbhd project template for default tools, and install '
                        'them on the project(s) if not already installed.')
    parser.add_argument('--validate-only', '-v', action='store_true', dest='validate_only',
                        help='Validate ALL records, make no changes')
    return parser.parse_args()


if __name__ == '__main__':
    sys.exit(main(parse_options()))
