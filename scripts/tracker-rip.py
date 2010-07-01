#!/usr/bin/python
import sys
import getpass
from urlparse import urljoin

from pyforge.lib import rest_api

SRC_CRED=dict(
        api_key='b15b105ee580a8652616',
        secret_key='d2a3315517ba81491ed7b7498636495023b8fb2d72e461457a20aa4b9e7ad032e9a8d07187f36661',
        http_username=raw_input('LDAP username: '),
        http_password=getpass.getpass('LDAP password: '))
SRC_SERVER='https://newforge.sf.geek.net/'
SRC_TOOL='/rest/p/forge/tickets/'

# Credentials for sf-overlords
DST_CRED=dict(
    api_key='a4a88c67179137053d70',
    secret_key='fcc48a0c31459e99a88cc42cdd7f908fad78b283ca30a86caac1ab65036ff71fc195a18e56534dc5')
DST_SERVER='http://sourceforge.net/'
DST_TOOL='/rest/p/forge/tickets/'

FAKE_TICKET={
    u'created_date': u'2010-03-08 17:29:42.802000',
    u'assigned_to_id': u'',
    u'assigned_to': u'',
    u'custom_fields': {'_component':'', '_size':0, '_priority':'', '_type':''},
    u'description': u'Ticket was not present in source',
    u'milestone': u'',
    u'reported_by': u'',
    u'reported_by_id': u'',
    u'status': u'closed',
    u'sub_ids': [],
    u'summary': u'Placeholder ticket',
    u'super_id': u'None'}

def main():
    src_cli = rest_api.RestClient(
        base_uri=SRC_SERVER,
        **SRC_CRED)
    dst_cli = rest_api.RestClient(
        base_uri=DST_SERVER,
        **DST_CRED)
    src = TicketAPI(src_cli, SRC_TOOL)
    dst = TicketAPI(dst_cli, DST_TOOL)
    for ticket in src.iter_tickets(check=True):
        print 'Migrating ticket %s:\n%s' % (ticket['ticket_num'], ticket)
        print 'Create ticket on %s' % DST_SERVER
        dst.create_ticket(ticket)
        print 'Create discussion on %s' % DST_SERVER
        src_thread = src.load_thread(ticket)
        if not src_thread or not src_thread['posts']:
            print '... no posts'
            continue
        dst_thread = dst.load_thread(ticket)
        slug_map = {}
        for post in src.iter_posts(src_thread):
            print '... migrate post %s:\n%r' % (post['slug'], post['text'])
            dst.create_post(dst_thread, post, slug_map)

class TicketAPI(object):

    def __init__(self, client, path):
        self.client = client
        self.path = path

    def iter_tickets(self, min_ticket=1, max_ticket=None, check=False):
        if check:
            tickets = self.client.request('GET', self.path)['tickets']
            valid_tickets = set(t['ticket_num'] for t in tickets)
            max_valid_ticket = max(valid_tickets)
        cur_ticket = min_ticket
        while True:
            if check and cur_ticket not in valid_tickets:
                if cur_ticket > max_valid_ticket: break
                yield dict(FAKE_TICKET, ticket_num=cur_ticket)
                cur_ticket += 1
                continue
            ticket = self.client.request('GET', self.ticket_path(cur_ticket))['ticket']
            if ticket is None: break
            yield ticket
            cur_ticket += 1
            if max_ticket and cur_ticket > max_ticket: break

    def load_thread(self, ticket):
        discussion = self.client.request('GET', self.discussion_path())['discussion']
        for thd in discussion['threads']:
            if thd['subject'].startswith('#%d ' % ticket['ticket_num']):
                break
        else:
            return None
        thread = self.client.request(
            'GET',self.thread_path(thd['_id']))['thread']
        return thread

    def iter_posts(self, thread):
        for p in sorted(thread['posts'], key=lambda p:p['slug']):
            post = self.client.request(
                'GET', self.post_path(thread['_id'], p['slug']))['post']
            yield post

    def create_ticket(self, ticket):
        ticket = dict(ticket, labels='')
        ticket['description'] = 'Created by: %s\nCreated date: %s\nAssigned to:%s\n\n%s' % (
            ticket['reported_by'], ticket['created_date'], ticket['assigned_to'], ticket['description'])
        for bad_key in ('assigned_to_id', 'created_date', 'reported_by', 'reported_by_id', 'super_id', 'sub_ids', '_id'):
            if bad_key in ticket:
                del ticket[bad_key]
        ticket.setdefault('labels', '')
        ticket['custom_fields'].setdefault('_size', 0)
        ticket['custom_fields'].setdefault('_priority', 'low')
        ticket['custom_fields'].setdefault('_type', 'Bug')
        ticket['custom_fields'].setdefault('_type', 'Component')
        if ticket['custom_fields']['_size'] is None:
            ticket['custom_fields']['_size'] = 0
        if ticket['milestone'] not in ('backlog', 'public2',  'GA', 'post-GA'):
            ticket['milestone'] = ''
        if ticket['status'] not in 'open in-progress code-review validation closed'.split():
            ticket['status'] = 'open'
        r = self.client.request('POST', self.new_ticket_path(), ticket_form=ticket)
        self.client.request(
            'POST', self.ticket_path(r['ticket']['ticket_num'], 'save'),
            ticket_form=ticket)

    def create_post(self, thread, post, slug_map):
        text = 'Post by %s:\n%s' % (
            post['author'], post['text'])
        if '/' in post['slug']:
            parent_post = slug_map[post['slug'].rsplit('/', 1)[0]]
            new_post = self.client.request(
                'POST', self.post_path(thread['_id'], parent_post, 'reply'),
                text=text)['post']
        else:
            new_post = self.client.request(
                'POST', self.thread_path(thread['_id'], 'new'),
                text=text)['post']
        slug_map[post['slug']] = new_post['slug']
        return new_post

    def new_ticket_path(self):
        return urljoin(self.path, 'new')

    def ticket_path(self, ticket_num, suffix=''):
        return urljoin(self.path, str(ticket_num)) + '/' + suffix

    def discussion_path(self):
        return '%s_discuss/' % (self.path)

    def thread_path(self, thread_id, suffix=''):
        return '%s_discuss/thread/%s/%s' % (self.path, thread_id, suffix)

    def post_path(self, thread_id, post_slug, suffix=''):
        return '%s_discuss/thread/%s/%s/%s' % (self.path, thread_id, post_slug, suffix)

def pm(etype, value, tb): # pragma no cover
    import pdb, traceback
    try:
        from IPython.ipapi import make_session; make_session()
        from IPython.Debugger import Pdb
        sys.stderr.write('Entering post-mortem IPDB shell\n')
        p = Pdb(color_scheme='Linux')
        p.reset()
        p.setup(None, tb)
        p.print_stack_trace()
        sys.stderr.write('%s: %s\n' % ( etype, value))
        p.cmdloop()
        p.forget()
        # p.interaction(None, tb)
    except ImportError:
        sys.stderr.write('Entering post-mortem PDB shell\n')
        traceback.print_exception(etype, value, tb)
        pdb.post_mortem(tb)

sys.excepthook = pm

if __name__ == '__main__':
    main()
