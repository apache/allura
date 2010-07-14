import logging

from ming.orm import ORMSession

from .model import MigrationInfo
from .migrate import Migration
from . import graph

log = logging.getLogger(__name__)

MIGRATION_GRAPH = None

def run_migration(datastore, target_versions, dry_run):
    '''Attempt to migrate the database to a specific set of required
    modules  & versions.'''
    # Get the migration status of the db
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    ormsession = ORMSession(session)
    info = MigrationInfo.m.get()
    if info is None:
        info = MigrationInfo.make({})
    latest_versions = Migration.latest_versions()
    for k,v in target_versions.iteritems():
        cur = info.versions.get(k, -1)
        islatest = ' (LATEST)' if v == latest_versions[k] else ''
        log.info('Target %s=%s%s (current=%s)', k, v, islatest, cur)
    # Create a migration plan
    plan = list(plan_migration(session, ormsession, info, target_versions))
    # Execute (or print) the plan
    for step in plan:
        log.info('Migrate %r', step)
        if dry_run: continue
        step.apply(info.versions)
        info.m.save()

def show_status(datastore):
    # Get the migration status of the db
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    info = MigrationInfo.m.get()
    if info is None:
        info = MigrationInfo.make({})
    for k,v in info.versions.iteritems():
        log.info('%s=%s', k, v)

def set_status(datastore, target_versions):
    # Get the migration status of the db
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    info = MigrationInfo.m.get()
    if info is None:
        info = MigrationInfo.make({})
    latest_versions = Migration.latest_versions()
    for k,v in target_versions.iteritems():
        cur = info.versions.get(k, -1)
        islatest = ' (LATEST)' if v == latest_versions[k] else ''
        log.info('FORCE %s=%s%s (current=%s)', k, v, islatest, cur)
    info.versions.update(target_versions)
    info.m.save()

def plan_migration(session, ormsession, info, target):
    '''Return the optimal list of graph.MigrationSteps to run in order to
    satisfy the target requirements'''
    global MIGRATION_GRAPH
    if MIGRATION_GRAPH is None:
        migrations = dict((k, v(session, ormsession))
                          for k,v in Migration.migrations_registry.iteritems())
        MIGRATION_GRAPH = graph.MigrationGraph(migrations)
    else:
        MIGRATION_GRAPH.reset()
    return MIGRATION_GRAPH.shortest_path(info.versions, target)

def reset_migration(datastore, dry_run):
    '''Reset the state of the database to non-version-controlled WITHOUT migrating

    This is equivalent to setting all the versions to -1.'''
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    log.info('Reset migrations')
    if not dry_run:
        MigrationInfo.m.remove()

