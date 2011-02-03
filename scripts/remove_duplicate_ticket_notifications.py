import sys
import logging
import re
from itertools import groupby

import pymongo
from ming.orm import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)

# Given a list of subscriptions, try to find one with a proper artifact_url, and delete the rest
# If none of them have artifact_urls, delete them all
def trim_subs(subs, test):
    prime = False

    print "Found %d '%s' subs with for user '%s'" % (len(subs), subs[0].artifact_title, str(subs[0].user_id))
    for sub in subs:
        if sub.artifact_url and not prime:
            prime = True
            print "   Keeping good subscription with a URL of '%s'" % sub.artifact_url
        else:
            if not sub.artifact_url:
                print "   Found subscription with no artifact URL, deleting."
            else:
                print "   Subscription has URL, but is a duplicate, deleting."
            if not test: sub.delete()


def main():
    test = sys.argv[-1] == 'test'
    title = re.compile('Ticket .*')
    all_subscriptions = M.Mailbox.query.find(dict(artifact_title=title, type='direct')).sort([ ('artifact_title', pymongo.ASCENDING), ('user_id', pymongo.DESCENDING) ]).all()
    log.info('Fixing duplicate tracker subscriptions')

    for (key, group) in groupby(
        all_subscriptions,
        key=lambda sub:(sub.artifact_title, sub.user_id)):
        group = list(group)
        if group:
            trim_subs(group, test)
    if not test: ThreadLocalORMSession.flush_all()


if __name__ == '__main__':
    main()
