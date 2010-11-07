import sys
from pprint import pprint
import csv
import urlparse
import urllib2
import json
import time
import re
from optparse import OptionParser
from itertools import islice
from datetime import datetime

import feedparser
from html2text import html2text
from BeautifulSoup import BeautifulSoup
import dateutil.parser
import pytz


def parse_options():
    optparser = OptionParser(usage=''' %prog <Trac URL>
 
Export ticket data from a Trac instance''')
    optparser.add_option('-o', '--out-file', dest='out_filename', help='Write to file (default stdout)')
    optparser.add_option('--attachments', dest='do_attachments', action='store_true', help='Export attachment info')
    optparser.add_option('--only-tickets', dest='only_tickets', action='store_true', help='Export only ticket list')
    optparser.add_option('--start', dest='start_id', type='int', default=1, help='Start with given ticket numer (or next accessible)')
    optparser.add_option('--limit', dest='limit', type='int', default=None, help='Limit number of tickets')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose operation')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments.")
    return options, args


class TracExport(object):

    PAGE_SIZE = 100
    TICKET_URL = '/ticket/%d'
    QUERY_MAX_ID_URL  = '/query?col=id&order=id&desc=1&max=2'
    QUERY_BY_PAGE_URL = '/query?col=id&col=time&col=changetime&order=id&max=' + str(PAGE_SIZE)+ '&page=%d'
    ATTACHMENT_LIST_URL = '/attachment/ticket/%d/'
    ATTACHMENT_URL = '/raw-attachment/ticket/%d/%s'

    FIELD_MAP = {
        'reporter': 'submitter',
        'owner': 'assigned_to',
    }

    def __init__(self, base_url, start_id=1):
        """start_id - start with at least that ticket number (actual returned
                      ticket may have higher id if we don't have access to exact 
                      one).
        """
        self.base_url = base_url
        # Contains additional info for a ticket which cannot
        # be get with single-ticket export (create/mod times is
        # and example).
        self.ticket_map = {}
        self.ticket_queue = []
        self.start_id = start_id
        self.page = (start_id - 1) / self.PAGE_SIZE + 1

    def remap_fields(self, dict):
        "Remap fields to adhere to standard taxonomy."
        out = {}
        for k, v in dict.iteritems():
            out[self.FIELD_MAP.get(k, k)] = v
            
        out['id'] = int(out['id'])
        if 'private' in out:
            out['private'] = bool(int(out['private']))
        return out

    def full_url(self, suburl, type=None):
        url = urlparse.urljoin(self.base_url, suburl)
        if type is None:
            return url
        glue = '&' if '?' in suburl else '?'
        return  url + glue + 'format=' + type

    @staticmethod
    def log_url(url):
        if options.verbose:
            print >>sys.stderr, url

    @classmethod
    def trac2z_date(cls, s):
        d = dateutil.parser.parse(s)
        d = d.astimezone(pytz.UTC)
        return d.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def match_pattern(regexp, string):
        m = re.match(regexp, string)
        assert m
        return m.group(1)

    def csvopen(self, url):
        self.log_url(url)
        f = urllib2.urlopen(url)
        # Trac doesn't throw 403 error, just shows normal 200 HTML page
        # telling that access denied. So, we'll emulate 403 ourselves.
        # TODO: currently, any non-csv result treated as 403.
        if not f.info()['Content-Type'].startswith('text/csv'):
            raise urllib2.HTTPError(url, 403, 'Forbidden - emulated', f.info(), f)
        return f

    def parse_ticket_body(self, id):
        # Use CSV export to get ticket fields
        url = self.full_url(self.TICKET_URL % id, 'csv')
        f = self.csvopen(url)
        reader = csv.DictReader(f)
        ticket_fields = reader.next()
        ticket_fields['class'] = 'ARTIFACT'
        return self.remap_fields(ticket_fields)

    def parse_ticket_comments(self, id):
        # Use RSS export to get ticket comments
        url = self.full_url(self.TICKET_URL % id, 'rss')
        self.log_url(url)
        d = feedparser.parse(url)
        res = []
        for comment in d['entries']:
            c = {}
            c['submitter'] = comment.author
            c['date'] = comment.updated_parsed
            c['comment'] = html2text(comment.summary)
            c['class'] = 'COMMENT'
            res.append(c)
        return res

    def parse_ticket_attachments(self, id):
        SIZE_PATTERN = r'(\d+) bytes'
        TIMESTAMP_PATTERN = r'(.+) in Timeline'
        # Scrape HTML to get ticket attachments
        url = self.full_url(self.ATTACHMENT_LIST_URL % id)
        self.log_url(url)
        f = urllib2.urlopen(url)
        soup = BeautifulSoup(f)
        attach = soup.find('div', id='attachments')
        assert attach
        list = []
        while True:
            attach = attach.findNext('dt')
            if not attach:
                break
            d = {}
            d['filename'] = attach.a['href'].rsplit('/', 1)[1]
            d['url'] = self.full_url(self.ATTACHMENT_URL % (id, d['filename']))
            size_s = attach.span['title']
            d['size'] = int(self.match_pattern(SIZE_PATTERN, size_s))
            timestamp_s = attach.find('a', {'class': 'timeline'})['title']
            d['date'] = self.trac2z_date(self.match_pattern(TIMESTAMP_PATTERN, timestamp_s))
            d['by'] = attach.find(text=re.compile('added by')).nextSibling.renderContents()
            desc_el = attach.findNext('dd')
            # TODO: Convert to Allura link syntax as needed
            d['description'] = ''.join(desc_el.findAll(text=True)).strip()
            list.append(d)
        return list

    def get_max_ticket_id(self):
        url = self.full_url(self.QUERY_MAX_ID_URL, 'csv')
        f = self.csvopen(url)
        reader = csv.DictReader(f)
        fields = reader.next()
        print fields
        return int(fields['id'])

    def get_ticket(self, id, extra={}):
        '''Get ticket with given id
        extra: extra fields to add to ticket (parsed elsewhere)
        '''
        t = self.parse_ticket_body(id)
        t['comments'] = self.parse_ticket_comments(id)
        if options.do_attachments:
            t['attachments'] = self.parse_ticket_attachments(id)
        t.update(extra)
        return t

    def next_ticket_ids(self):
        'Go thru ticket list and collect available ticket ids.'
        # We could just do CSV export, which by default dumps entire list
        # Alas, for many busy servers with long ticket list, it will just 
        # time out. So, let's paginate it instead.
        res = []

        url = self.full_url(self.QUERY_BY_PAGE_URL % self.page, 'csv')
        try:
            f = self.csvopen(url)
        except urllib2.HTTPError, e:
            if 'emulated' in e.msg:
                body = e.fp.read()
                if 'beyond the number of pages in the query' in body:
                    raise StopIteration
            raise
        reader = csv.reader(f)
        cols = reader.next()
        for r in reader:
            if r and r[0].isdigit():
                id = int(r[0])
                extra = {'date': self.trac2z_date(r[1]), 'date_updated': self.trac2z_date(r[2])}
                res.append((id, extra))
        self.page += 1

        return res

    def __iter__(self):
        return self

    def next(self):
        while True:
            if not self.ticket_queue:
                self.ticket_queue = self.next_ticket_ids()
            id, extra = self.ticket_queue.pop(0)
            if id >= self.start_id:
                break
        return self.get_ticket(id, extra)
            
        
class DateJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, time.struct_time):
            return time.strftime('%Y-%m-%dT%H:%M:%SZ', obj)
        return json.JSONEncoder.default(self, obj)

if __name__ == '__main__':
    options, args = parse_options()
    ex = TracExport(args[0], start_id=options.start_id)
    # Implement iterator sequence limiting using islice()
    doc = [t for t in islice(ex, options.limit)]

    if not options.only_tickets:
        doc = {
            'class': 'PROJECT',
            'trackers': {'default': {'artifacts': doc}}
        }

    out_file = sys.stdout
    if options.out_filename:
        out_file = open(options.out_filename, 'w')
    out_file.write(json.dumps(doc, cls=DateJSONEncoder, indent=2, sort_keys=True))
    # It's bad habit not to terminate lines
    out_file.write('\n')
