import logging

from .model import MigrationInfo
from .migrate import Migration

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

def reset_migration(datastore, dry_run):
    '''Reset the state of the database to non-version-controlled WITHOUT migrating

    This is equivalent to setting all the versions to -1.'''
    session = MigrationInfo.__mongometa__.session
    session.bind = datastore
    log.info('Reset migrations')
    if not dry_run:
        MigrationInfo.m.remove()

class MigrationStep(object):

    def __init__(self, session, module, version, direction):
        self.module = module
        self.version = version
        self.direction = direction
        self.session = session
        self.migration = Migration.get(module, version)(session)
        if direction == 'up':
            self.requires = dict(self.migration.requires())
            self.postcondition = {module:version}
        else:
            self.requires = {module:version}
            self.postcondition = {module:version-1}

    def __repr__(self):
        return '<%s on %s.%s>' % (self.direction, self.module, self.version)

    def apply(self, state):
        state.update(self.postcondition)
        if self.direction == 'up':
            self.migration.up()
        else:
            self.migration.down()

    def unmet_requirements(self, state):
        result = {}
        for k,v in self.requires.iteritems():
            if state.get(k, -1) != v: result[k] = v
        return result

    def precluded_by(self, other_step):
        for k,v in self.requires.iteritems():
            if other_step.postcondition.get(k, v) != v:
                return True
        return False

    def add_requirements(self, steps, req):
        if self.direction == 'down':
            mod,ver = self.module, self.version-1
            if (mod,ver) in steps: return
            if req[mod] == ver: return
            step = MigrationStep(self.session, mod, ver, 'down')
            steps[mod,ver] = step
            step.add_requirements(steps, req)
        for mod, ver in self.requires.iteritems():
            if (mod,ver) in steps: continue
            if ver != -1:
                step = MigrationStep(self.session, mod, ver, self.direction)
                steps[mod,ver] = step
                step.add_requirements(steps, req)

def plan_migration(session, info, target_versions):
    '''Create a migration plan based on the current DB state and the
    target version set'''
    # Determine all the (final) migrations that need to be run
    steps = {}
    for mod,req_ver in target_versions.iteritems():
        cur_ver = info.versions.get(mod, -1)
        if cur_ver < req_ver:
            steps[mod,req_ver] = MigrationStep(session, mod, req_ver, 'up')
        elif cur_ver > req_ver:
            steps[mod,cur_ver] = MigrationStep(session, mod, cur_ver, 'down')
    # Add the dependencies of all the migrations
    current = dict(info.versions)
    for step in steps.values():
        step.add_requirements(steps, target_versions)
    # Schedule migrations to be run
    steps = sorted(steps.values(), key=lambda s:(s.version, s.module))
    log.debug('Migrations to be run: %r', steps)
    while steps:
        step = _pop_step(steps, current)
        log.info('State %s, step %s', current, step)
        yield step
        current.update(step.postcondition)

def _pop_step(steps, current):
    '''This method looks at all the available migration steps and the current
    current versioning state and chooses a migration step to run next, removing it
    from the list of available migration steps and returning it.
    '''
    # Find all "valid" migrations, i.e. migrations whose requirements() are met
    valid = []
    invalid = []
    for s in steps:
        if s.unmet_requirements(current):
            invalid.append(s)
        else:
            valid.append(s)
    # If there's only one valid migration, then it's the next one we'll run
    if len(valid) == 1:
        steps[:] = invalid
        return valid[0]
    # Find a migration that does not preclude other valid migrations
    #   from running
    for i, step_a in enumerate(valid):
        for j, step_b in enumerate(valid):
            if i == j: continue # don't check against self
            if step_b.precluded_by(step_a): break # conflict, step_a is not next
        else:
            # No conflicts found, step_a is the next step
            # Remove step_a from the list of steps
            steps[:] = [ s for s in steps if s is not step_a ]
            return step_a
    # No next step found, could be circular dependency.  Log the error and raise
    # a ValueError
    log.error('Cannot find valid step at state %s', current)
    for v in valid:
        log.error('  %r', v)
    raise ValueError, "Plan stuck"
