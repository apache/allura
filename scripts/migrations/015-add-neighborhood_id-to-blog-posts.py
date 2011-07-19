import sys
import logging

from pylons import c
from ming.orm import session
from ming.orm.ormsession import ThreadLocalORMSession

from forgeblog import model as BM

log = logging.getLogger(__name__)

def main():
    broken_posts = BM.BlogPost.query.find(dict(neighborhood_id=None)).all()
    for post in broken_posts:
        c.project = post.app.project
        c.app = post.app
        post.neighborhood_id = post.app.project.neighborhood_id
        ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()