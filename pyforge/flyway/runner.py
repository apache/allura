import logging

from .model import MigrationInfo
from .migrate import Migration
from . import graph

log = logging.getLogger(__name__)

def run_migration(datastore, target_versions, dry_run):
    '''Attempt to migrate the database to a specific set of required
    modules  & versions.'''
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
        log.info('Target %s=%s%s (current=%s)', k, v, islatest, cur)
    # Create a migration plan
    plan = list(plan_migration(session, info, target_versions))
    # Execute (or print) the plan
    for step in plan:
        log.info('Migrate %r', step)
        if dry_run: continue
        step.apply(info.versions)
        info.m.save()

def plan_migration(session, info, target):
    '''Return the optimal list of graph.MigrationSteps to run in order to
    satisfy the target requirements'''
    migrations = dict((k, v(session))
                      for k,v in Migration.migrations_registry.iteritems())
    g = graph.MigrationGraph(migrations)
    return g.shortest_path(info.versions, target)

def reset_migration(datastore, dry_run):
    '''Reset the state of the database to non-version-controlled WITHOUT migrating

    This is equivalent to setting all the versions to -1.'''
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    log.info('Reset migrations')
    if not dry_run:
        MigrationInfo.m.remove()

