from forgewiki.command.base import WikiCommand
from forgewiki.command.wiki2markdown.extractors import MySQLExtractor
from forgewiki.command.wiki2markdown.loaders import MediawikiLoader
from allura.command import base as allura_base


class Wiki2MarkDownCommand(WikiCommand):
    min_args = 1
    max_args = None
    summary = 'Import wiki from mediawiki-dump to allura wiki'

    parser = WikiCommand.standard_parser(verbose=True)
    parser.add_option('-e', '--extract-only', action='store_true',
                      dest='extract',
                      help='Store data from the mediawiki-dump'
                      'on the local filesystem; not load into Allura')
    parser.add_option('-l', '--load-only', action='store_true', dest='load',
                help='Load into Allura previously-extracted data')
    parser.add_option('-d', '--dump-dir', dest='dump_dir', default='',
                help='Directory for dump files')
    parser.add_option('-n', '--neighborhood', dest='nbhd', default='',
                help='Neighborhood name to load data')
    parser.add_option('-p', '--project', dest='project', default='',
                help='Project shortname to load data into')
    parser.add_option('-s', '--source', dest='source', default='',
                help='Database type to extract from (only mysql for now)')
    parser.add_option('--db_name', dest='db_name', default='mediawiki',
                help='Database name')
    parser.add_option('--host', dest='host', default='localhost',
                help='Database host')
    parser.add_option('--port', dest='port', type='int', default=0,
                help='Database port')
    parser.add_option('--user', dest='user', default='',
                help='User for database connection')
    parser.add_option('--password', dest='password', default='',
                help='Password for database connection')

    def command(self):
        self.basic_setup()
        self.handle_options()

        if self.options.extract:
            self.extractor.extract()
        if self.options.load:
            self.loader = MediawikiLoader(self.options)
            self.loader.load()

    def handle_options(self):
        if self.options.dump_dir == '':
            allura_base.log.error('You must specify directory for dump files')
            exit(2)

        if not self.options.extract and not self.options.load:
            # if action doesn't specified - do both
            self.options.extract = True
            self.options.load = True

        if self.options.load and (not self.options.project
                                  or not self.options.nbhd):
            allura_base.log.error('You must specify neighborhood and project '
                                  'to load data')
            exit(2)

        if self.options.extract:
            if self.options.source == 'mysql':
                self.extractor = MySQLExtractor(self.options)
            elif self.options.source in ('sqlite', 'postgres', 'sql-dump'):
                allura_base.log.error('This source not implemented yet.'
                                      'Only mysql for now')
                exit(2)
            else:
                allura_base.log.error('You must specify valid data source')
                exit(2)
