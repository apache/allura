import logging

from allura import model as M

log = logging.getLogger(__name__)


def main():
    M.Mailbox.query.update({'queue': []},
                           {'$set': {'queue_empty': True}},
                           multi=True)

    M.Mailbox.query.update({'queue': {'$ne': []}},
                           {'$set': {'queue_empty': False}},
                           multi=True)

if __name__ == '__main__':
    main()
