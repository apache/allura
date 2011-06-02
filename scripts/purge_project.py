import sys
import logging

from pylons import g, c

from ming.orm import session, Mapper

from allura import model as M

log = logging.getLogger(__name__)


def main():
    USAGE='Usage: %s <shortname> [test]' % sys.argv[0]
    if len(sys.argv) not in (2,3):
        log.error(USAGE)
        return 1
    if len(sys.argv) == 3 and sys.argv[2] != 'test':
        log.error(USAGE)
        return 1
    pname = sys.argv[1]
    log.info('Purging %s', pname)
    project = M.Project.query.get(shortname=pname)
    if project is None:
        log.fatal('Project %s not found', pname)
        return 2
    if len(sys.argv) == 3:
        log.info('Test mode, not purging project')
    else:
        purge_project(project)
    return 0

def purge_project(project):
    gid = project.tool_data.get('sfx', {}).get('group_id', project._id)
    project.shortname = 'deleted-%s' % gid
    project.deleted = True
    g.solr.delete(q='project_id_s:%s' % project._id)
    session(project).flush()
    c.project = project
    app_config_ids = [
        ac._id for ac in M.AppConfig.query.find(dict(project_id=c.project._id)) ]
    for m in Mapper.all_mappers():
        cls = m.mapped_class
        if 'project_id' in m.property_index:
            # Purge the things directly related to the project
            cls.query.remove(
                dict(project_id=project._id),
            )
        elif 'app_config_id' in m.property_index:
            # ... and the things related to its apps
            cls.query.remove(
                dict(app_config_id={'$in':app_config_ids}),
            )
        else:
            # Don't dump other things
            continue

if __name__ == '__main__':
    sys.exit(main())
