import logging

import pkg_resources
from pymongo.connection import Connection
from paste.script import command

from ming.datastore import DataStore
from ming.utils import parse_uri

class MigrateCommand(command.Command):
    min_args = 0
    group_name = 'Flyway'
    summary = 'Migrate the Ming schema'
    usage = 'NAME [options] [module=version...]'
    entry_point_section='flyway.migrations'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-u', '--url', dest='connection_url',
                      default='mongo://127.0.0.1:27017/',
                      help='MongoDB url to migrate')
    parser.add_option('-l', '--logging', dest='logging_config_file',
                      default=None)
    parser.add_option('--log-level', dest='log_level', default='INFO')
    parser.add_option('--reset', dest='reset', action='store_true', default=False)
    parser.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False)
    parser.add_option('-s', '--status', dest='status_only', action='store_true', default=False)
    parser.add_option('--force', dest='force', action='store_true', default=False)

    def command(self):
        self._setup_logging()
        self._load_migrations()
        from .runner import run_migration, reset_migration, show_status, set_status
        parsed_connection_url = parse_uri(self.options.connection_url)
        if not parsed_connection_url['path']:
            parsed_connection_url['path'] += '/'
        if parsed_connection_url['path'] == '/':
            # Find all the databases managed by the server
            connection = Connection(
                parsed_connection_url['host'],
                parsed_connection_url['port'])
            datastores = [ DataStore(self.options.connection_url + db)
                           for db in connection.database_names()
                           if db not in ('admin', 'local')]
        else:
            datastores = [ DataStore(self.options.connection_url) ]
        self.log.info('Migrate server: %s:%s',
                      parsed_connection_url['host'],
                      parsed_connection_url['port'])
        for ds in datastores:
            self.log.info('Migrate DB: %s', ds.database)
            if self.options.status_only:
                show_status(ds)
            elif self.options.force:
                set_status(ds, self._target_versions())
            elif self.options.reset:
                reset_migration(ds, dry_run=self.options.dry_run)
            else:
                run_migration(ds, self._target_versions(), dry_run=self.options.dry_run)
            try:
                ds.conn.disconnect()
                ds._conn = None
            except: # MIM doesn't do this
                pass

    def _setup_logging(self):
        if self.options.logging_config_file: # pragma no cover
            logging.config.fileConfig(self.options.logging_config_file)
        else:
            logging.basicConfig(
                level=logging._levelNames[self.options.log_level],
                format='%(asctime)s,%(msecs)03d %(levelname)-5.5s'
                ' [%(name)s]  %(message)s',
                datefmt='%H:%M:%S')
        self.log = logging.getLogger(__name__)

    def _target_versions(self):
        from .migrate import Migration
        latest_versions = Migration.latest_versions()
        if self.args:
            target = {}
            for a in self.args:
                if '=' in a:
                    k,v = a.split('=')
                    target[k] = int(v)
                else:
                    target[a] = latest_versions[a]
            return target
        else:
            return latest_versions

    def _load_migrations(self):
        from .migrate import Migration
        Migration.migrations_registry.clear()
        for ep in pkg_resources.iter_entry_points(self.entry_point_section):
            self.log.debug('Loading migration module %s', ep.name)
            Migration._current_migrations_module = ep.name
            reload(ep.load())
            Migration._current_migrations_module = None
