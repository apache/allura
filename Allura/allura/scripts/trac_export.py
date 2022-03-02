#!/usr/bin/env python

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging
import sys
import csv
import six.moves.urllib.parse
import six.moves.urllib.request
import six.moves.urllib.error
import json
import time
import re
from optparse import OptionParser
from itertools import islice
from io import TextIOWrapper

from bs4 import BeautifulSoup, NavigableString
import dateutil.parser
import pytz
import six

try:
    from forgeimporters.base import ProjectExtractor
    urlopen = ProjectExtractor.urlopen
except ImportError:
    try:
        from allura.lib.helpers import urlopen
    except ImportError:
        from six.moves.urllib.request import urlopen

log = logging.getLogger(__name__)


def parse_options():
    optparser = OptionParser(usage=''' %prog <Trac URL>

Export ticket data from a Trac instance''')
    optparser.add_option('-o', '--out-file', dest='out_filename',
                         help='Write to file (default stdout)')
    optparser.add_option('--no-attachments', dest='do_attachments',
                         action='store_false', default=True, help='Export attachment info')
    optparser.add_option('--only-tickets', dest='only_tickets',
                         action='store_true', help='Export only ticket list')
    optparser.add_option('--start', dest='start_id', type='int', default=1,
                         help='Start with given ticket numer (or next accessible)')
    optparser.add_option('--limit', dest='limit', type='int',
                         default=None, help='Limit number of tickets')
    optparser.add_option('-v', '--verbose', dest='verbose',
                         action='store_true', help='Verbose operation')
    options, args = optparser.parse_args()
    if len(args) != 1:
        optparser.error("Wrong number of arguments.")
    return options, args


class TracExport:

    PAGE_SIZE = 100
    TICKET_URL = 'ticket/%s'
    QUERY_MAX_ID_URL = 'query?col=id&order=id&desc=1&max=2'
    QUERY_BY_PAGE_URL = 'query?col=id&col=time&col=changetime&order=id&max=' + \
        str(PAGE_SIZE) + '&page=%d'
    ATTACHMENT_LIST_URL = 'attachment/ticket/%d/'
    ATTACHMENT_URL = 'raw-attachment/ticket/%d/%s'

    FIELD_MAP = {
        'reporter': 'submitter',
        'owner': 'assigned_to',
    }

    def __init__(self, base_url, start_id=1, verbose=False, do_attachments=True):
        """start_id - start with at least that ticket number (actual returned
                      ticket may have higher id if we don't have access to exact
                      one).
        """
        self.base_url = base_url.rstrip('/') + '/'
        # Contains additional info for a ticket which cannot
        # be get with single-ticket export (create/mod times is
        # and example).
        self.ticket_map = {}
        self.start_id = start_id
        self.page = (start_id - 1) // self.PAGE_SIZE + 1
        self.verbose = verbose
        self.do_attachments = do_attachments
        self.exhausted = False
        self.ticket_queue = self.next_ticket_ids()

    def remap_fields(self, dict):
        "Remap fields to adhere to standard taxonomy."
        out = {}
        for k, v in dict.items():
            key = self.match_pattern(r'\W*(\w+)\W*', k)
            out[self.FIELD_MAP.get(key, key)] = v

        out['id'] = int(out['id'])
        if 'private' in out:
            out['private'] = bool(int(out['private']))
        return out

    def full_url(self, suburl, type=None):
        url = six.moves.urllib.parse.urljoin(self.base_url, suburl)
        if type is None:
            return url
        glue = '&' if '?' in suburl else '?'
        return url + glue + 'format=' + type

    def log_url(self, url):
        log.info(url)
        if self.verbose:
            print(url, file=sys.stderr)

    @classmethod
    def trac2z_date(cls, s):
        d = dateutil.parser.parse(s)
        if d.tzinfo is not None:
            d = d.astimezone(pytz.UTC)
        return d.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def match_pattern(regexp, string):
        m = re.match(regexp, string)
        assert m, f"'{regexp}' didn't match '{string}'"
        for grp in m.groups():
            if grp is not None:
                return grp
        return None

    def csvopen(self, url):
        self.log_url(url)
        f = urlopen(url)
        # Trac doesn't throw 403 error, just shows normal 200 HTML page
        # telling that access denied. So, we'll emulate 403 ourselves.
        # TODO: currently, any non-csv result treated as 403.
        if not f.info()['Content-Type'].startswith('text/csv'):
            raise six.moves.urllib.error.HTTPError(
                url, 403, 'Forbidden - emulated', f.info(), f)
        return TextIOWrapper(f)

    def parse_ticket(self, id):
        # Use CSV export to get ticket fields
        url = self.full_url(self.TICKET_URL % id, 'csv')
        f = self.csvopen(url)
        reader = csv.DictReader(f)
        ticket_fields = next(reader)
        ticket_fields['class'] = 'ARTIFACT'
        ticket = self.remap_fields(ticket_fields)

        # Use HTML export to get ticket description and comments
        import html2text
        html2text.BODY_WIDTH = 0
        url = self.full_url(self.TICKET_URL % id)
        self.log_url(url)
        d = BeautifulSoup(urlopen(url))
        self.clean_missing_wiki_links(d)
        desc = d.find('div', 'description').find('div', 'searchable')
        ticket['description'] = html2text.html2text(
            desc.renderContents('utf8').decode('utf8')) if desc else ''
        comments = []
        relative_base_url = six.moves.urllib.parse.urlparse(self.full_url(self.TICKET_URL % '')).path
        for comment in d.findAll('form', action='#comment'):
            c = {}
            c['submitter'] = re.sub(
                r'.* by ', '', comment.find('h3', 'change').text).strip()
            c['date'] = self.trac2z_date(
                comment.find('a', 'timeline')['title'].replace(' in Timeline', '').replace('See timeline at ', ''))
            changes = str(comment.find('ul', 'changes') or '')
            body = comment.find('div', 'comment')
            body = body.renderContents('utf8').decode('utf8') if body else ''
            body = body.replace(f'href="{relative_base_url}', 'href="')  # crude way to rewrite ticket links
            c['comment'] = html2text.html2text(changes + body)
            c['class'] = 'COMMENT'
            comments.append(c)
        ticket['comments'] = comments
        return ticket

    def parse_ticket_attachments(self, id):
        SIZE_PATTERN = r'(\d+) bytes'
        TIMESTAMP_PATTERN = r'(?:(.+) in Timeline|See timeline at (.+))'
        # Scrape HTML to get ticket attachments
        url = self.full_url(self.ATTACHMENT_LIST_URL % id)
        self.log_url(url)
        f = urlopen(url)
        soup = BeautifulSoup(f)
        attach = soup.find('div', id='attachments')
        list = []
        while attach:
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
            d['by'] = attach.find(text=re.compile('added by')).nextSibling.text
            d['description'] = ''
            # Skip whitespace
            while attach.nextSibling and isinstance(attach.nextSibling, NavigableString):
                attach = attach.nextSibling
            # if there's a description, there will be a <dd> element, other
            # immediately next <dt>
            if attach.nextSibling and attach.nextSibling.name == 'dd':
                desc_el = attach.nextSibling
                if desc_el:
                    # TODO: Convert to Allura link syntax as needed
                    d['description'] = ''.join(
                        desc_el.findAll(text=True)).strip()
            list.append(d)
        return list

    def get_max_ticket_id(self):
        url = self.full_url(self.QUERY_MAX_ID_URL, 'csv')
        f = self.csvopen(url)
        reader = csv.DictReader(f)
        fields = next(reader)
        print(fields)
        return int(fields['id'])

    def get_ticket(self, id, extra={}):
        '''Get ticket with given id
        extra: extra fields to add to ticket (parsed elsewhere)
        '''
        t = self.parse_ticket(id)
        if self.do_attachments:
            atts = self.parse_ticket_attachments(id)
            if atts:
                t['attachments'] = atts
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
        except six.moves.urllib.error.HTTPError as e:
            if 'emulated' in e.msg:
                body = e.fp.read()
                if 'beyond the number of pages in the query' in six.ensure_text(body):
                    raise StopIteration
            raise
        reader = csv.reader(f)
        cols = next(reader)
        for r in reader:
            if r and r[0].isdigit():
                id = int(r[0])
                extra = {'date': self.trac2z_date(r[1]),
                         'date_updated': self.trac2z_date(r[2])}
                res.append((id, extra))
        self.page += 1

        if len(res) < self.PAGE_SIZE:
            self.exhausted = True

        return res

    def __iter__(self):
        return self

    def next(self):
        while True:
            # queue empty, try to fetch more
            if len(self.ticket_queue) == 0 and not self.exhausted:
                self.ticket_queue = self.next_ticket_ids()
            # there aren't any more, we're really done
            if len(self.ticket_queue) == 0:
                raise StopIteration
            id, extra = self.ticket_queue.pop(0)
            if id >= self.start_id:
                break
        return self.get_ticket(id, extra)
    __next__ = next

    def clean_missing_wiki_links(self, doc):
        for link in doc.findAll('a', 'missing wiki'):
            link.string = link.string.rstrip('?')


class DateJSONEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, time.struct_time):
            return time.strftime('%Y-%m-%dT%H:%M:%SZ', obj)
        return json.JSONEncoder.default(self, obj)


def export(url, start_id=1, verbose=False, do_attachments=True,
           only_tickets=False, limit=None, **kw):
    ex = TracExport(url, start_id=start_id,
                    verbose=verbose, do_attachments=do_attachments)

    doc = [t for t in islice(ex, limit)]

    if not only_tickets:
        doc = {
            'class': 'PROJECT',
            'trackers': {'default': {'artifacts': doc}}
        }
    return doc


def main():
    options, args = parse_options()
    doc = export(args[0], **vars(options))

    out_file = sys.stdout
    if options.out_filename:
        out_file = open(options.out_filename, 'w', encoding='utf-8')
    out_file.write(
        json.dumps(doc, cls=DateJSONEncoder, indent=2, sort_keys=True))
    # It's bad habit not to terminate lines
    out_file.write('\n')


if __name__ == '__main__':
    main()
