import sys
import logging

from ming.orm.ormsession import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

def main():
    M.TroveCategory(trove_cat_id=905,
                    trove_parent_id=14,
                    shortname='mpl20',
                    fullname='Mozilla Public License 2.0 (MPL 2.0)',
                    fullpath='License :: OSI-Approved Open Source :: Mozilla Public License 2.0 (MPL 2.0)')

    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
