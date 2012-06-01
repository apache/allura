import logging
import sys

from ming.orm import ThreadLocalORMSession
import mock
from pylons import c, g

from allura import model as M
from forgediscussion import model as DM
from forgetracker import model as TM

from allura.lib import utils

log = logging.getLogger(__name__)


def public(obj, project=None):
    if not project:
        project = obj
    role_anon = M.ProjectRole.by_name(name='*anonymous', project=project)
    if not role_anon:
        log.info('Missing *anonymous role for project "%s"' %
                project.shortname)
        return False
    read = M.ACE.allow(role_anon._id, 'read')
    return read in obj.acl


def scrub_project(p, options):
    log.info('Scrubbing project "%s"' % p.shortname)
    preamble = options.preamble
    if not public(p):
        log.info('%s project "%s"' % (preamble, p.shortname))
        if not options.dry_run:
            p.delete()
        return
    for ac in p.app_configs:
        ac.project = p
        c.app = p.app_instance(ac)
        mount_point = ac.options.get('mount_point')
        if ac.tool_name in ('admin', 'search', 'profile'):
            continue
        if not public(ac, project=p):
            log.info('%s tool %s/%s on project "%s"' % (
                preamble, ac.tool_name, mount_point, p.shortname))
            if not options.dry_run:
                p.uninstall_app(mount_point)
            continue
        q = dict(app_config_id=ac._id)
        ace = dict(access='DENY', permission='*', role_id=None)
        q['acl'] = {'$in': [ace]}
        counter = 0
        if ac.tool_name == 'Tickets':
            for tickets in utils.chunked_find(TM.Ticket, q):
                for t in tickets:
                    counter += 1
                    if not options.dry_run:
                        t.discussion_thread.delete()
                        t.delete()
                ThreadLocalORMSession.flush_all()
                ThreadLocalORMSession.close_all()
            if counter > 0:
                log.info('%s %s tickets from the %s/%s tool on '
                         'project "%s"' % (preamble, counter, ac.tool_name,
                             mount_point, p.shortname))
        elif ac.tool_name == 'Discussion':
            for forums in utils.chunked_find(DM.Forum, q):
                for f in forums:
                    counter += 1
                    if not options.dry_run:
                        f.delete()
            if counter > 0:
                log.info('%s %s forums from the %s/%s tool on '
                         'project "%s"' % (preamble, counter, ac.tool_name,
                             mount_point, p.shortname))


def main(options):
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(getattr(logging, options.log_level.upper()))

    g.solr = mock.Mock()
    preamble = options.dry_run and "Would delete" or "Deleting"
    options.preamble = preamble

    for nbhd in M.Neighborhood.query.find():
        q = {'neighborhood_id': nbhd._id}
        for projects in utils.chunked_find(M.Project, q):
            for p in projects:
                scrub_project(p, options)
            ThreadLocalORMSession.flush_all()
            ThreadLocalORMSession.close_all()

    log.info('%s %s EmailAddress documents' %
            (preamble, M.EmailAddress.query.find().count()))
    log.info('%s email addresses from %s User documents' %
            (preamble, M.User.query.find().count()))
    if not options.dry_run:
        M.EmailAddress.query.remove()
        M.User.query.update({}, {"$set": {"email_addresses": []}}, multi=True)

    return 0


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(
            description='Removes private data from the Allura MongoDB.')
    parser.add_argument('--dry-run', dest='dry_run', default=False,
            action='store_true',
            help='Run in test mode (no updates will be applied).')
    parser.add_argument('--log', dest='log_level', default='INFO',
            help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    return parser.parse_args()

if __name__ == '__main__':
    sys.exit(main(parse_options()))
