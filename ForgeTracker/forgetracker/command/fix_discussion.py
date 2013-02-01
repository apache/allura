from bson import ObjectId
from bson.errors import InvalidId

from allura.command import base
from allura import model as M
from allura.lib import exceptions as exc


class FixDiscussion(base.Command):
    """Fixes trackers that had used buggy 'ticket move' feature before it was fixed.

    See [#5727] for details.

    Usage:

    paster fix-discussion ../Allura/development.ini [project_name_or_id]

    If used with optional parameter will fix trackers for specified project,
    else will fix all trackers in all projects.
    """
    group_name = 'ForgeTracker'
    min_args = 1
    max_args = 2
    usage = '<ini file> [project_name_or_id]'
    summary = "Fix trackers that had used buggy 'ticket move' feature"
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()

        if len(self.args) >= 2:
            p_name_or_id = self.args[1]
            try:
                project = M.Project.query.get(_id=ObjectId(p_name_or_id))
            except InvalidId:
                projects = M.Project.query.find({'$or': [
                    {'shortname': p_name_or_id},
                    {'name': p_name_or_id}
                ]})
                if projects.count() > 1:
                    raise exc.ForgeError('Multiple projects has a shortname %s. '
                            'Use project _id instead.' % p_name_or_id)
                project = projects.first()
            if not project:
                raise exc.NoSuchProjectError('The project %s '
                        'could not be found' % p_name_or_id)

            self.fix_for_project(project)
        else:
            base.log.info('Checking discussion instances for each tracker in all projects')

    def fix_for_project(self, project):
        base.log.info('Checking discussion instances for each tracker in project %s' % project.shortname)
