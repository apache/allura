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
            # change 'deny write' and 'write' permission
            role_ids = [(p.role_id, p.access) for p in a.acl if p.permission == 'write']
            for role_id, access in role_ids:
                if access == M.ACE.DENY:
                    a.acl.add(M.ACE.deny(role_id, 'create'))
                    a.acl.add(M.ACE.deny(role_id, 'update'))
                else:
                    a.acl.add(M.ACE.allow(role_id, 'create'))
                    a.acl.add(M.ACE.allow(role_id, 'update'))

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
