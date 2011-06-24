"""
Remove the subject FieldProperty from all ForumPost objects. [#2071]
"""

import logging
import sys

from ming.orm import state

from allura import model as M
from forgediscussion import model as DM

log = logging.getLogger(__name__)

c_forumpost = M.project_doc_session.db.forum_post

def main():
    test = sys.argv[-1] == 'test'

    forum_posts = c_forumpost.find()
    for fp in forum_posts:
        try:
            s = fp['subject']
            if test:
                log.info('... would remove subject "%s" from %s', s, fp['_id'])
            else:
                log.info('... removing subject "%s" from %s', s, fp['_id'])
                del fp['subject']
                c_forumpost.save(fp)
        except KeyError:
            log.info('... no subject property on %s', fp['_id'])

if __name__ == '__main__':
    main()
