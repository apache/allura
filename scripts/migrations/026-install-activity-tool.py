import logging

from ming.orm import ThreadLocalORMSession

from allura.lib import utils
from allura import model as M

log = logging.getLogger(__name__)

def main():
    for chunk in utils.chunked_find(M.Project):
        for p in chunk:
            p.install_app('activity')

        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()
