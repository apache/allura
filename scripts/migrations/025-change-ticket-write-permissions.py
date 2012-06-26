import logging
import re

from pylons import c

from ming.orm import ThreadLocalORMSession

from allura import model as M

from allura.lib import utils
from forgetracker import model as TM
from forgewiki.wiki_main import ForgeWikiApp

log = logging.getLogger(__name__)


# migration script for change write permission to create + update
def main():
    query = {'tool_name': {'$regex': '^tickets$', '$options': 'i'}}
    for chunk in utils.chunked_find(M.AppConfig, query):
        for a in chunk:
            # change 'write' permission
            it = (i for i, v in enumerate(a.acl) if v.permission == 'write')
            for i in it:
                role_id = a.acl[i].role_id
                del a.acl[i]
                a.acl.append(M.ACE.allow(role_id, 'create'))
                a.acl.append(M.ACE.allow(role_id, 'update'))
            # change 'deny write' permission
            it = (i for i, v in enumerate(a.acl)
                    if v.permission == 'deny write')
            for i in it:
                role_id = a.acl[i].role_id
                del a.acl[i]
                a.acl.append(M.ACE.allow(role_id, 'deny create'))
                a.acl.append(M.ACE.allow(role_id, 'deny update'))

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
