'''Attempt to create/update all the projects on the SFX side
'''
import sys
import logging

from tg import config
from pylons import c

from pyforge import model as M
from pyforge.lib import helpers as h
from pyforge.lib.security import roles_with_project_access
from pyforge.ext.sfx.lib.sfx_api import SFXProjectApi

log = logging.getLogger(__name__)

if config['auth.method'] != 'sfx': sys.exit(0)
api = SFXProjectApi()
n = M.Neighborhood.query.get(name='Projects')
for p in n.projects:
    with h.push_config(c, project=p):
        developers = [
            pr.user
            for pr in roles_with_project_access('update', p)
            if pr.user is not None and pr.user.sfx_userid is not None ]
        if developers:
            log.info('Re-registering project %s with main admin %s', p.shortname, developers[0])
        else:
            log.error("Can't reregister project %s; no developers exist", p.shortname)
            continue
        api.create(developers[0], n, p.shortname, p.short_description)
        api.update(developers[0], p)
