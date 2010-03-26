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
    State, modules, states = graph.gen_migration_states(migrations)
    state_index = graph.index_migration_states(modules, states)
    nodes = graph.build_graph(states, state_index, migrations)
    start = dict((m, -1) for m in modules)
    start.update(info.versions)
    end_states = set(graph.states_with(target.items(), state_index))
    start_node = [ n for n in nodes if State(**start) == n.data ][0]
    end_nodes = set(n for n in nodes if n.data in end_states)
    path = graph.shortest_path(nodes, start_node, end_nodes)
    return [
        s for s in path
        if isinstance(s, graph.MigrateStep) ]

def reset_migration(datastore, dry_run):
    '''Reset the state of the database to non-version-controlled WITHOUT migrating

    This is equivalent to setting all the versions to -1.'''
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    log.info('Reset migrations')
    if not dry_run:
        MigrationInfo.m.remove()

