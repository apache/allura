import logging

from allura import model as M

log = logging.getLogger(__name__)

print 'In a script'
log.info('in a script')

for p in M.Project.query.find():
    log.info('Project %s: %s (%s)', p.shortname, p.name, p.short_description)
assert M.Project.query.find().count()
