import sys
import logging

from tg import config
from pylons import c

from pyforge import model as M
from pyforge.lib import helpers as h
from pyforge.lib.security import roles_with_project_access
from pyforge.ext.sfx.lib.sfx_api import SFXProjectApi

log = logging.getLogger(__name__)

print 'In a script'
log.info('in a script')

for p in M.Project.query.find():
    log.info('Project %s: %s (%s)', p.shortname, p.name, p.short_description)
assert M.Project.query.find().count()
