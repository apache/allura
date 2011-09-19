import sys
import logging

from pylons import c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

def main():
    M.TroveCategory(trove_cat_id=862,
                    trove_parent_id=14,
                    shortname="lppl",
                    fullname="LaTeX Project Public License",
                    fullpath="License :: OSI-Approved Open Source :: LaTeX Project Public License")
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()