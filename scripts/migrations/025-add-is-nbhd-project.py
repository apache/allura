import logging
import re

from pylons import tmpl_context as c

from ming.orm import ThreadLocalORMSession, session

from allura import model as M

log = logging.getLogger(__name__)

def main():
    M.Project.query.update({'shortname': '--init--'}, {'$set': {'is_nbhd_project': True}}, multi=True)
    M.Project.query.update({'shortname': {'$ne': '--init--'}}, {'$set': {'is_nbhd_project': False}}, multi=True)

if __name__ == '__main__':
    main()
