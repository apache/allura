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
    for a in M.AppConfig.query.find().all():
        if a.tool_name == "tickets":
            is_deleted = True
            while is_deleted:
                is_deleted = False
                for i in range(len(a.acl)):
                    if a.acl[i].permission == "write":
                        del a.acl[i]
                        a.acl.append(M.ACE.allow(a.acl[i].role_id, 'update'))
                        a.acl.append(M.ACE.allow(a.acl[i].role_id, 'create'))
                        is_deleted = True
                        break

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
