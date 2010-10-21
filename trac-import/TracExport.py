from pprint import pprint
import csv
import urllib2
from cStringIO import StringIO
import json
import time

import feedparser
from html2text import html2text

from allura.lib import rest_api


class TracExport(object):

    TICKET_URL = '/ticket/%d'
    QUERY_MAX_ID_URL  = '/query?col=id&order=id&desc=1&max=2'
    QUERY_BY_PAGE_URL = '/query?col=id&order=id&max=100&page=%d'

    FIELD_MAP = {
        'reporter': 'submitter',
        'owner': 'assigned_to',
    }

    def __init__(self, base_url):
        self.base_url = base_url

    def remap_fields(self, dict):
        "Remap fields to adhere to standard taxonomy."
        out = {}
        for k, v in dict.iteritems():
            out[self.FIELD_MAP.get(k, k)] = v
            
        if 'private' in out:
            out['private'] = bool(int(out['private']))
        return out

    def full_url(self, suburl, type):
        glue = '&' if '?' in suburl else '?'
        return self.base_url + suburl + glue + 'format=' + type

    def csvopen(self, url):
        print url
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
        d = feedparser.parse(self.full_url(self.TICKET_URL % id, 'rss'))
    #    pprint.pprint(d['entries'])
        res = []
        for comment in d['entries']:
            c = {}
            c['submitter'] = comment.author
            c['date'] = comment.updated_parsed
            c['comment'] = html2text(comment.summary)
            c['class'] = 'COMMENT'
            res.append(c)
        return res

    def get_ticket(self, id):
        t = self.parse_ticket_body(id)
        t['comments'] = self.parse_ticket_comments(id)
        return t

    def get_ticket_ids_csv(self):
        url = self.full_url(self.QUERY_URL, 'csv')
        print url
        f = urllib2.urlopen(url, timeout=None)
        reader = csv.reader(f)
        cols = reader.next()
        ids = [r for r in reader]
        return ids

    def get_ticket_ids(self):
        # As Trac has only one tracker, and number ticket sequantally, 
        # We have two choices here:
        # 1. Get the last existing ticket id, and just make sequence
        #    from 1 to that id. But then we should be ready to teh fact
        #    that some tickets in this range will be unavailable.
        # 2. Export artifact list and get ids which are really accessible
        #    to the current user.
        # It turns out that we need to paginate artifact list, so it's
        # some time and extra traffic, so first method used by default.
        if False:
            max = self.get_max_ticket_id()
            return xrange(1, max + 1)
        else:
            return self.enumerate_ticket_ids()

    def get_max_ticket_id(self):
        url = self.full_url(self.QUERY_MAX_ID_URL, 'csv')
        f = self.csvopen(url)
        reader = csv.DictReader(f)
        fields = reader.next()
        print fields
        return int(fields['id'])
        
    def enumerate_ticket_ids(self, page=1):
        'Go thru ticket list and collect available ticket ids.'
        # We could just do CSV export, which by default dumps entire list
        # Alas, for many busy servers with long ticket list, it will just 
        # time out. So, let's paginate it instead.
        res = []
        while True:
            url = self.full_url(self.QUERY_BY_PAGE_URL % page, 'csv')
            try:
                f = self.csvopen(url)
            except urllib2.HTTPError, e:
                if 'emulated' in e.msg:
                    body = e.fp.read()
                    if 'beyond the number of pages in the query' in body:
                        break
                raise
            reader = csv.reader(f)
            cols = reader.next()
            ids = [int(r[0]) for r in reader if r and r[0][0].isdigit()]
            res += ids
            page += 1

        return res
        
class DateJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, time.struct_time):
            return time.strftime('%Y-%m-%dT%H:%M:%SZ', obj)
        return json.JSONEncoder.default(self, obj)

if __name__ == '__main__':
    TRAC_BASE_URL = 'http://sourceforge.net/apps/trac/sourceforge'
    ex = TracExport(TRAC_BASE_URL)
#    d = ex.parse_ticket_body(9)
#    pprint(d)
#    d = ex.parse_ticket_comments(9)
#    pprint(d)
#    d = ex.get_ticket(9)
#    pprint(d)
#    d = ex.get_max_ticket_id()
#    d = ex.get_ticket_ids()
    ids = [3]
    doc = [ex.get_ticket(i) for i in ids]
    print json.dumps(doc, cls=DateJSONEncoder, indent=2)

