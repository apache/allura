import logging

from pylons import c

from ming.orm import ThreadLocalORMSession

from forgewiki import model as WM

log = logging.getLogger(__name__)

def main():
    c.project = None
    pages = WM.Page.query.find({'title': {'$regex': '\/'}}).all()
    print 'Found %s wiki titles containing "/"...' % len(pages)
    for page in pages:
        page.title = page.title.replace('/', '-')
        print 'Updated: %s' % page.title
    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
