import logging

from tg import config

from ming.orm import session

import sfx
from allura import model as M
from allura.lib import helpers as h
from sfx.model import tables as T

log = logging.getLogger(__name__)

def main():
    sfx.middleware.configure_databases(h.config_with_prefix(config, 'sfx.'))
    topic_trove = T.trove_cat.select(T.trove_cat.c.shortname=='topic').execute().fetchone()
    M.ProjectCategory.query.remove()
    for t in T.trove_cat.select(
        T.trove_cat.c.parent==topic_trove.trove_cat_id).execute():
        parent = M.ProjectCategory(name=t.shortname, label=t.fullname, description=t.description)
        for tt in T.trove_cat.select(
            T.trove_cat.c.parent==t.trove_cat_id).execute():
            M.ProjectCategory(parent_id=parent._id,
                              name=tt.shortname, label=tt.fullname, description=tt.description)
    session(M.ProjectCategory).flush()

if __name__ == '__main__':
    main()
