import sys
import logging

from pylons import c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils

log = logging.getLogger('update-ordinals')
log.addHandler(logging.StreamHandler(sys.stdout))

def main():
    test = sys.argv[-1] == 'test'
    num_projects_examined = 0
    log.info('Examining all projects for mount order.')
    for some_projects in utils.chunked_find(M.Project):
        for project in some_projects:
            c.project = project
            mounts = project.ordered_mounts(include_search=True)

            # ordered_mounts() means duplicate ordinals (if any) will be next to each other
            duplicates_found = False
            prev_ordinal = None
            for mount in mounts:
                if mount['ordinal'] == prev_ordinal:
                    duplicates_found = True
                    break
                prev_ordinal = mount['ordinal']

            if duplicates_found:
                if test:
                    log.info('Would renumber mounts for project "%s".' % project.shortname)
                else:
                    log.info('Renumbering mounts for project "%s".' % project.shortname)
                    for i, mount in enumerate(mounts):
                        if 'ac' in mount:
                            mount['ac'].options['ordinal'] = i
                        elif 'sub' in mount:
                            mount['sub'].ordinal = i
                    ThreadLocalORMSession.flush_all()

            num_projects_examined += 1
            session(project).clear()

        log.info('%s projects examined.' % num_projects_examined)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
