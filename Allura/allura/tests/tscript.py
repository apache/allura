import sys
import logging

from tg import config
from pylons import c

from allura import model as M
from allura.lib import helpers as h

log = logging.getLogger(__name__)

print 'In a script'
log.info('in a script')

for p in M.Project.query.find():
    log.info('Project %s: %s (%s)', p.shortname, p.name, p.short_description)
assert M.Project.query.find().count()
