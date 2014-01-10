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
import logging
import shutil
import tempfile

from tg import config

from allura.lib import helpers as h
from allura.scripts import ScriptTask

from forgewiki.scripts.wiki2markdown.extractors import MySQLExtractor
from forgewiki.scripts.wiki2markdown.loaders import MediawikiLoader

log = logging.getLogger(__name__)


class Wiki2Markdown(ScriptTask):

    """Import MediaWiki to Allura Wiki tool"""
    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Import wiki from'
                                         'mediawiki-dump to allura wiki')
        parser.add_argument('-e', '--extract-only', action='store_true',
                            dest='extract',
                            help='Store data from the mediawiki-dump '
                            'on the local filesystem; not load into Allura')
        parser.add_argument(
            '-l', '--load-only', action='store_true', dest='load',
            help='Load into Allura previously-extracted data')
        parser.add_argument('-d', '--dump-dir', dest='dump_dir', default='',
                            help='Directory for dump files')
        parser.add_argument('-n', '--neighborhood', dest='nbhd', default='',
                            help='Neighborhood name to load data')
        parser.add_argument('-p', '--project', dest='project', default='',
                            help='Project shortname to load data into')
        parser.add_argument('-a', '--attachments-dir', dest='attachments_dir',
                            help='Path to directory with mediawiki attachments dump',
                            default='')
        parser.add_argument('--db_config_prefix', dest='db_config_prefix',
                            help='Key prefix (e.g. "legacy.") in ini file to '
                            'use instead of commandline db params')
        parser.add_argument('-s', '--source', dest='source', default='mysql',
                            help='Database type to extract from (only mysql for now)')
        parser.add_argument('--db_name', dest='db_name', default='mediawiki',
                            help='Database name')
        parser.add_argument('--host', dest='host', default='localhost',
                            help='Database host')
        parser.add_argument('--port', dest='port', type=int, default=0,
                            help='Database port')
        parser.add_argument('--user', dest='user', default='',
                            help='User for database connection')
        parser.add_argument('--password', dest='password', default='',
                            help='Password for database connection')
        parser.add_argument(
            '--keep-dumps', action='store_true', dest='keep_dumps',
            help='Leave dump files on disk after run')
        return parser

    @classmethod
    def execute(cls, options):
        options = cls.handle_options(options)

        try:
            if options.extract:
                MySQLExtractor(options).extract()
            if options.load:
                MediawikiLoader(options).load()
        finally:
            if not options.keep_dumps:
                shutil.rmtree(options.dump_dir)

    @classmethod
    def handle_options(cls, options):
        if not options.extract and not options.load:
            # if action doesn't specified - do both
            options.extract = True
            options.load = True

        if not options.dump_dir:
            if options.load and not options.extract:
                raise ValueError(
                    'You must specify directory containing dump files')
            else:
                options.dump_dir = tempfile.mkdtemp()
                log.info("Writing temp files to %s", options.dump_dir)

        if options.load and (not options.project or not options.nbhd):
            raise ValueError('You must specify neighborhood and project '
                             'to load data')

        if options.extract:
            if options.db_config_prefix:
                for k, v in h.config_with_prefix(config, options.db_config_prefix).iteritems():
                    if k == 'port':
                        v = int(v)
                    setattr(options, k, v)

            if options.source == 'mysql':
                pass
            elif options.source in ('sqlite', 'postgres', 'sql-dump'):
                raise ValueError(
                    'This source not implemented yet. Only mysql for now')
            else:
                raise ValueError('You must specify a valid data source')

            if not options.attachments_dir:
                raise ValueError(
                    'You must specify path to directory with mediawiki attachmets dump.')

        return options


if __name__ == '__main__':
    Wiki2Markdown.main()
