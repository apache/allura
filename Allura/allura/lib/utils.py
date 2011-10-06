import time
import string
import hashlib
import binascii
import logging
import random
import mimetypes
from itertools import groupby
from logging.handlers import WatchedFileHandler

import tg
import pylons
import webob.multidict
from formencode import Invalid
from tg.decorators import before_validate
from pylons import response
from pylons import tmpl_context as c
from paste.httpheaders import CACHE_CONTROL, EXPIRES
from webhelpers.html import literal
from webob import exc

from ew import jinja2_ew as ew
from ming.utils import LazyProperty

def permanent_redirect(url):
    try:
        tg.redirect(url)
    except exc.HTTPFound, err:
        raise exc.HTTPMovedPermanently(location=err.location)

def cache_forever():
    headers = [
        (k,v) for k,v in response.headers.items()
        if k.lower() not in ('pragma', 'cache-control') ]
    delta = CACHE_CONTROL.apply(
        headers,
        public=True,
        max_age=60*60*24*365)
    EXPIRES.update(headers, delta=delta)
    response.headers.pop('cache-control', None)
    response.headers.pop('pragma', None)
    response.headers.update(headers)

class memoize_on_request(object):

    def __init__(self, *key, **kwargs):
        self.key = key
        self.include_func_in_key = kwargs.pop(
            'include_func_in_key', False)
        assert not kwargs, 'Extra args'

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            cache = c.memoize_cache
            if self.include_func_in_key:
                key = (func, self.key, args, tuple(kwargs.iteritems()))
            else:
                key = (self.key, args, tuple(kwargs.iteritems()))
            if key in cache:
                result = cache[key]
            else:
                result = cache[key] = func(*args, **kwargs)
            return result
        wrapper.__name__ = 'wrap(%s)' % func.__name__
        return wrapper

def guess_mime_type(filename):
    '''Guess MIME type based on filename.
    Applies heuristics, tweaks, and defaults in centralized manner.
    '''
    # Consider changing to strict=False
    content_type = mimetypes.guess_type(filename, strict=True)
    if content_type[0]:
        content_type = content_type[0]
    else:
        content_type = 'application/octet-stream'
    return content_type

class ConfigProxy(object):
    '''Wrapper for loading config values at module-scope so we don't
    have problems when a module is imported before tg.config is initialized
    '''

    def __init__(self, **kw):
        self._kw = kw

    def __getattr__(self, k):
        return tg.config[self._kw[k]]

class lazy_logger(object):
    '''Lazy instatiation of a logger, to ensure that it does not get
    created before logging is configured (which would make it disabled)'''

    def __init__(self, name):
        self._name = name

    @LazyProperty
    def _logger(self):
        return logging.getLogger(self._name)

    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError, name
        return getattr(self._logger, name)

class StatsHandler(WatchedFileHandler):
    fields=('action', 'action_type', 'tool_type', 'tool_mount', 'project', 'neighborhood',
            'username', 'url', 'ip_address')

    def __init__(self,
                 strftime_pattern,
                 module='allura',
                 page=1,
                 **kwargs):
        self.page = page
        self.module = module
        WatchedFileHandler.__init__(self, strftime_pattern)

    def emit(self, record):
        if not hasattr(record, 'action'):
            return
        kwpairs = dict(
            module=self.module,
            page=self.page)
        for name in self.fields:
            kwpairs[name] = getattr(record, name, None)
        kwpairs.update(getattr(record, 'kwpairs', {}))
        record.kwpairs = ','.join(
            '%s=%s' % (k,v) for k,v in sorted(kwpairs.iteritems())
            if v is not None)
        record.exc_info = None # Never put tracebacks in the rtstats log
        WatchedFileHandler.emit(self, record)

def chunked_find(cls, query=None, pagesize=1024):
    if query is None: query = {}
    page = 0
    while True:
        results = (
            cls.query.find(query)
            .skip(pagesize*page)
            .limit(pagesize)
            .all())
        if not results: break
        yield results
        page += 1

def lsub_utf8(s, n):
    '''Useful for returning n bytes of a UTF-8 string, rather than characters'''
    while len(s) > n:
        k = n
        while (ord(s[k]) & 0xc0) == 0x80:
            k -= 1
        return s[:k]
    return s


def chunked_iter(iterable, max_size):
    '''return iterable 'chunks' from the iterable of max size max_size'''
    eiter = enumerate(iterable)
    keyfunc = lambda (i,x): i//max_size
    for _, chunk in groupby(eiter, keyfunc):
        yield (x for i,x in chunk)

class AntiSpam(object):
    '''Helper class for bot-protecting forms'''
    honey_field_template=string.Template('''<p class="$honey_class">
    <label for="$fld_id">You seem to have CSS turned off.
        Please don't fill out this field.</label><br>
    <input id="$fld_id" name="$fld_name" type="text"><br></p>''')

    def __init__(self, request=None, num_honey=2):
        self.num_honey = num_honey
        if request is None or request.method == 'GET':
            self.request = pylons.request
            self.timestamp = int(time.time())
            self.spinner = self.make_spinner()
            self.timestamp_text = str(self.timestamp)
            self.spinner_text = self._wrap(self.spinner)
        else:
            self.request = request
            self.timestamp_text = request.params['timestamp']
            self.spinner_text = request.params['spinner']
            self.timestamp = int(self.timestamp_text)
            self.spinner = self._unwrap(self.spinner_text)
        self.spinner_ord = map(ord, self.spinner)
        self.random_padding = [ random.randint(0,255) for x in self.spinner ]
        self.honey_class = self.enc(self.spinner_text, css_safe=True)

        # The counter is to ensure that multiple forms in the same page
        # don't end up with the same id.  Instead of doing:
        #
        # honey0, honey1
        # which just relies on 0..num_honey we include a counter
        # which is incremented every time extra_fields is called:
        #
        # honey00, honey 01, honey10, honey11
        self.counter = 0

    @staticmethod
    def _wrap(s):
        '''Encode a string to make it HTML id-safe (starts with alpha, includes
        only digits, hyphens, underscores, colons, and periods).  Luckily, base64
        encoding doesn't use hyphens, underscores, colons, nor periods, so we'll
        use these characters to replace its plus, slash, equals, and newline.
        '''
        tx_tbl = string.maketrans('+/', '-_')
        s = binascii.b2a_base64(s)
        s = s.rstrip('=\n')
        s = s.translate(tx_tbl)
        s = 'X' + s
        return s

    @staticmethod
    def _unwrap(s):
        tx_tbl = string.maketrans('-_', '+/')
        s = s[1:]
        s = str(s).translate(tx_tbl)
        i = len(s) % 4
        if i > 0:
            s += '=' * (4 - i)
        s = binascii.a2b_base64(s + '\n')
        return s

    def enc(self, plain, css_safe=False):
        '''Stupid fieldname encryption.  Not production-grade, but
        hopefully "good enough" to stop spammers.  Basically just an
        XOR of the spinner with the unobfuscated field name
        '''
        # Plain starts with its length, includes the ordinals for its
        #   characters, and is padded with random data
        plain = ([ len(plain) ]
                 + map(ord, plain)
                 + self.random_padding[:len(self.spinner_ord) - len(plain) - 1])
        enc = ''.join(chr(p^s) for p, s in zip(plain, self.spinner_ord))
        enc = self._wrap(enc)
        if css_safe:
            enc = ''.join(ch for ch in enc if ch.isalpha())
        return enc

    def dec(self, enc):
        enc = self._unwrap(enc)
        enc = list(map(ord, enc))
        plain = [e^s for e,s in zip(enc, self.spinner_ord)]
        plain = plain[1:1+plain[0]]
        plain = ''.join(map(chr, plain))
        return plain

    def extra_fields(self):
        yield ew.HiddenField(name='timestamp', value=self.timestamp_text).display()
        yield ew.HiddenField(name='spinner', value=self.spinner_text).display()
        for fldno in range(self.num_honey):
            fld_name = self.enc('honey%d' % (fldno))
            fld_id = self.enc('honey%d%d' % (self.counter, fldno))
            yield literal(self.honey_field_template.substitute(
                    honey_class=self.honey_class,
                    fld_id=fld_id,
                    fld_name=fld_name))
        self.counter += 1

    def make_spinner(self, timestamp=None):
        if timestamp is None: timestamp = self.timestamp
        try:
            client_ip = self.request.headers.get('X_FORWARDED_FOR', self.request.remote_addr)
            client_ip = client_ip.split(',')[0].strip()
        except (TypeError, AttributeError), err:
            client_ip = '127.0.0.1'
        plain = '%d:%s:%s' % (
            timestamp, client_ip, pylons.config.get('spinner_secret', 'abcdef'))
        return hashlib.sha1(plain).digest()

    @classmethod
    def validate_request(cls, request=None, now=None, params=None):
        if request is None: request = pylons.request
        if params is None: params = request.params
        new_params = dict(params)
        if not request.method == 'GET':
            new_params.pop('timestamp', None)
            new_params.pop('spinner', None)
            obj = cls(request)
            if now is None: now = time.time()
            if obj.timestamp > now + 5:
                raise ValueError, 'Post from the future'
            if now - obj.timestamp > 60*60:
                raise ValueError, 'Post from the 1hr+ past'
            if obj.spinner != obj.make_spinner(obj.timestamp):
                raise ValueError, 'Bad spinner value'
            for k in new_params.keys():
                new_params[obj.dec(k)] = new_params.pop(k)
            for fldno in range(obj.num_honey):
                value = new_params.pop('honey%s' % fldno)
                if value:
                    raise ValueError, 'Value in honeypot field: %s' % value
        return new_params

    @classmethod
    def validate(cls, error_msg):
        '''Controller decorator to raise Invalid errors if bot protection is engaged'''
        def antispam_hook(remainder, params):
            '''Converts various errors in validate_request to a single Invalid message'''
            try:
                new_params = cls.validate_request(params=params)
                params.update(new_params)
            except (ValueError, TypeError, binascii.Error):
                raise Invalid(error_msg, params, None)
        return before_validate(antispam_hook)

class TruthyCallable(object):
    '''
    Wraps a callable to make it truthy in a boolean context.

    Assumes the callable returns a truthy value and can be called with no args.
    '''
    def __init__(self, callable):
        self.callable = callable
    def __call__(self, *args, **kw):
        return self.callable(*args, **kw)
    def __nonzero__(self):
        return self.callable()

class CaseInsensitiveDict(dict):

    def __init__(self, *args, **kwargs):
        super(CaseInsensitiveDict, self).__init__(*args, **kwargs)
        self._reindex()

    def _reindex(self):
        items = self.items()
        self.clear()
        self._index = {}
        for k,v in items:
            self[k] = v
        assert len(self) == len(items), 'Duplicate (case-insensitive) key'

    def __getitem__(self, name):
        return super(CaseInsensitiveDict, self).__getitem__(name.lower())

    def __setitem__(self, name, value):
        lname = name.lower()
        super(CaseInsensitiveDict, self).__setitem__(lname, value)
        self._index[lname] = name

    def __delitem__(self, name):
        super(CaseInsensitiveDict, self).__delitem__(name.lower())

    def pop(self, k, *args):
        return super(CaseInsensitiveDict, self).pop(k.lower(), *args)

    def popitem(self):
        k,v = super(CaseInsensitiveDict, self).popitem()
        return self._index[k], v

    def update(self, *args, **kwargs):
        super(CaseInsensitiveDict, self).update(*args, **kwargs)
        self._reindex()

def postmortem_hook(etype, value, tb): # pragma no cover
    import sys, pdb, traceback
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
