import logging

from tg import config

from ming.orm import ThreadLocalORMSession

import sfx
from allura import model as M
from allura.lib import helpers as h
from sfx.model import tables as T

log = logging.getLogger(__name__)

def main():
    sfx.middleware.configure_databases(h.config_with_prefix(config, 'sfx.'))
    parent_only_troves = T.trove_cat.select(T.trove_cat.c.parent_only==1).execute()
    parent_only_ids = [t.trove_cat_id for t in parent_only_troves]
    allura_troves = M.TroveCategory.query.find(dict(
        trove_cat_id={'$in': parent_only_ids})).all()
    print 'Found %s parent-only troves in alexandria.' % len(parent_only_ids)
    print 'Setting parent-only Allura troves...'
    for t in allura_troves:
        print ' %s: %s' % (t.trove_cat_id, t.fullpath)
        t.parent_only = True
    print 'Updated %s Allura troves.' % len(allura_troves)
    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
