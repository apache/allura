import logging
import sys

from ming.orm import ThreadLocalORMSession
from pylons import g

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

from sfx.lib.sfx_api import SFXProjectApi

log = logging.getLogger(__name__)

def main(options):
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(getattr(logging, options.log_level.upper()))

    api = SFXProjectApi()
    nbhd = M.Neighborhood.query.get(name=options.neighborhood)
    if not nbhd:
        return 'Invalid neighborhood "%s".' % options.neighborhood
    sfx_siteadmin = M.User.query.get(username=api.sfx_siteadmin)
    if not sfx_siteadmin:
        return "Couldn't find sfx_siteadmin with username '%s'" % api.sfx_siteadmin

    q = {'neighborhood_id': nbhd._id,
            'shortname': {'$ne':'--init--'}, 'deleted':False}
    private_count = public_count = 0
    for projects in utils.chunked_find(M.Project, q):
        for p in projects:
            role_anon = M.ProjectRole.upsert(name='*anonymous',
                    project_id=p.root_project._id)
            if M.ACE.allow(role_anon._id, 'read') not in p.acl:
                if options.test:
                    log.info('Would be made public: "%s"' % p.shortname)
                else:
                    log.info('Making public: "%s"' % p.shortname)
                    p.acl.append(M.ACE.allow(role_anon._id, 'read'))
                    ThreadLocalORMSession.flush_all()
                    try:
                        api.update(sfx_siteadmin, p)
                    except Exception, e:
                        log.warning('SFX API update failed for project "%s": '
                                    '%s' % (p.shortname, e))
                private_count += 1
            else:
                log.info('Already public: "%s"' % p.shortname)
                public_count += 1

    log.info('Already public: %s' % public_count)
    if options.test:
        log.info('Would be made public: %s' % private_count)
    else:
        log.info('Made public: %s' % private_count)
    return 0

def parse_options():
    import argparse
    parser = argparse.ArgumentParser(
            description='Make all projects in a neighborhood public.')
    parser.add_argument('neighborhood', metavar='NEIGHBORHOOD', type=str,
            help='Neighborhood name.')
    parser.add_argument('--test', dest='test', default=False,
            action='store_true',
            help='Run in test mode (no updates will be applied).')
    parser.add_argument('--log', dest='log_level', default='INFO',
            help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    return parser.parse_args()

if __name__ == '__main__':
    sys.exit(main(parse_options()))
