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
from __future__ import annotations

import base64
from collections.abc import Iterable
from contextlib import contextmanager
import time
import string
import hashlib
import binascii
import logging.handlers
import os.path
import datetime
import random
import mimetypes
import re
from typing import Type, TypeVar
import magic
from itertools import groupby
import operator as op
import collections
import ming
from six.moves.urllib.parse import urlparse
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import socket

import tg
import emoji
import json
from collections import OrderedDict

from bs4 import BeautifulSoup
from tg import redirect, app_globals as g
from tg.decorators import before_validate
from tg.controllers.util import etag_cache
from paste.deploy.converters import asbool, asint
from markupsafe import Markup
from webob import exc
from pygments.formatters import HtmlFormatter
from setproctitle import getproctitle
import html5lib.filters.sanitizer
from ew import jinja2_ew as ew
from ming.utils import LazyProperty
from ming.odm.odmsession import ODMCursor
from ming.odm import session
import six


T = TypeVar('T')


MARKDOWN_EXTENSIONS = ['.markdown', '.mdown', '.mkdn', '.mkd', '.md']


def clean_ming_config(config):
    # delete replicaSet=''
    for key in list(config.keys()):
        if '.replicaSet' in key and not config[key]:
            del config[key]
        elif 'mongo_host' in key and 'replicaSet=&' in config[key]:
            config[key] = config[key].replace('replicaSet=&', '')
    return config


def configure_ming(conf):
    conf = clean_ming_config(conf)
    ming.configure(**conf)


def permanent_redirect(url):
    try:
        tg.redirect(url)
    except exc.HTTPFound as err:
        raise exc.HTTPMovedPermanently(location=err.location)


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


class ConfigProxy:

    '''Wrapper for loading config values at module-scope so we don't
    have problems when a module is imported before tg.config is initialized
    '''

    def __init__(self, **kw):
        self._kw = kw

    def __getattr__(self, k):
        return self.get(k)

    def get(self, key, default=None):
        return tg.config.get(self._kw.get(key, key), default)

    def get_bool(self, key):
        return asbool(self.get(key))


class lazy_logger:

    '''Lazy instatiation of a logger, to ensure that it does not get
    created before logging is configured (which would make it disabled)'''

    def __init__(self, name):
        self._name = name

    @LazyProperty
    def _logger(self):
        return logging.getLogger(self._name)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._logger, name)


log = lazy_logger(__name__)


class CustomWatchedFileHandler(logging.handlers.WatchedFileHandler):

    """Custom log handler for Allura"""

    def format(self, record):
        """Prepends current process name to ``record.name`` if running in the
        context of a taskd process that is currently processing a task.

        """
        title = getproctitle()
        if title.startswith('taskd:'):
            record.name = f"{title}:{record.name}"
        return super().format(record)


def chunked_find(cls: Type[T], query: dict | None = None, pagesize: int = 1024, sort_key: str | None = '_id',
                 sort_dir: int = 1) -> Iterable[Iterable[T]]:
    '''
    Execute a mongo query against the specified class, yield some results at
    a time (avoids mongo cursor timeouts if the total result set is very large).

    Pass an indexed sort_key for efficient queries.  Default _id should work
    in most cases.
    '''
    if query is None:
        query = {}
    page = 0
    max_id = None
    while True:
        if sort_key:
            if max_id:
                if sort_key not in query:
                    query[sort_key] = {}
                query[sort_key]['$gt'] = max_id
            q = cls.query.find(query).limit(pagesize).sort(sort_key, sort_dir)
        else:
            # skipping requires scanning, even for an indexed query
            q = cls.query.find(query).limit(pagesize).skip(pagesize * page)
        results = q.all()
        if not results:
            break
        if sort_key:
            max_id = results[-1][sort_key]
        yield results
        if len(results) < pagesize:
            break
        page += 1


def chunked_list(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in range(0, len(l), n):
        yield l[i:i + n]


def chunked_iter(iterable, max_size):
    '''return iterable 'chunks' from the iterable of max size max_size'''
    eiter = enumerate(iterable)
    keyfunc = lambda i_x: i_x[0] // max_size
    for _, chunk in groupby(eiter, keyfunc):
        yield (x for i, x in chunk)


class AntiSpam:

    '''Helper class for bot-protecting forms'''
    honey_field_template = string.Template('''<p class="$honey_class">
    <label for="$fld_id">You seem to have CSS turned off.
        Please don't fill out this field.</label><br>
    <input id="$fld_id" name="$fld_name" type="text"><br></p>''')

    def __init__(self, request=None, num_honey=2, timestamp=None, spinner=None):
        self.num_honey = num_honey
        if request is None or request.method == 'GET':
            self.request = tg.request
            self.timestamp = timestamp if timestamp else int(time.time())
            self.spinner = spinner if spinner else self.make_spinner()
            self.timestamp_text = str(self.timestamp)
            self.spinner_text = six.ensure_text(self._wrap(self.spinner))
        else:
            self.request = request
            self.timestamp_text = request.params['timestamp']
            self.spinner_text = request.params['spinner']
            self.timestamp = int(self.timestamp_text)
            self.spinner = self._unwrap(self.spinner_text)
        trans_fn = int
        self.spinner_ord = list(map(trans_fn, self.spinner))
        self.random_padding = [random.randint(0, 255) for x in self.spinner]
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
        '''Encode bytes to make it HTML id-safe (starts with alpha, includes
        only digits, hyphens, underscores, colons, and periods).  Luckily, base64
        encoding doesn't use hyphens, underscores, colons, nor periods, so we'll
        use these characters to replace its plus, slash, equals, and newline.
        '''
        s = base64.b64encode(six.ensure_binary(s))
        s = s.rstrip(b'=\n')
        s = s.replace(b'+', b'-').replace(b'/', b'_')
        s = b'X' + s
        return s

    @staticmethod
    def _unwrap(s):
        s = s[1:]
        s = six.ensure_binary(s)
        s = s.replace(b'-', b'+').replace(b'_', b'/')
        i = len(s) % 4
        if i > 0:
            s += b'=' * (4 - i)
        s = base64.b64decode(s + b'\n')
        return s

    def enc(self, plain, css_safe=False):
        '''Stupid fieldname encryption.  Not production-grade, but
        hopefully "good enough" to stop spammers.  Basically just an
        XOR of the spinner with the unobfuscated field name
        '''
        # Plain starts with its length, includes the ordinals for its
        #   characters, and is padded with random data

        # limit to plain ascii, which should be sufficient for field names
        # I don't think the logic below would work with non-ascii multi-byte text anyway
        plain.encode('ascii')

        plain = ([len(plain)]
                 + list(map(ord, plain))
                 + self.random_padding[:len(self.spinner_ord) - len(plain) - 1])
        enc = ''.join(chr(p ^ s) for p, s in zip(plain, self.spinner_ord))
        enc = six.ensure_binary(enc)
        enc = self._wrap(enc)
        enc = six.ensure_text(enc)
        if css_safe:
            enc = ''.join(ch for ch in enc if ch.isalpha())
        return enc

    def dec(self, enc):
        enc = self._unwrap(enc)
        enc = six.ensure_text(enc)
        enc = list(map(ord, enc))
        plain = [e ^ s for e, s in zip(enc, self.spinner_ord)]
        plain = plain[1:1 + plain[0]]
        plain = ''.join(map(chr, plain))
        return plain

    def extra_fields(self):
        yield ew.HiddenField(name='timestamp', value=self.timestamp_text).display()
        yield ew.HiddenField(name='spinner', value=self.spinner_text).display()
        for fldno in range(self.num_honey):
            fld_name = self.enc('honey%d' % (fldno))
            fld_id = self.enc('honey%d%d' % (self.counter, fldno))
            yield Markup(self.honey_field_template.substitute(
                honey_class=self.honey_class,
                fld_id=fld_id,
                fld_name=fld_name))
        self.counter += 1

    def make_spinner(self, timestamp=None):
        if timestamp is None:
            timestamp = self.timestamp
        try:
            self.client_ip = ip_address(self.request)
        except (TypeError, AttributeError):
            self.client_ip = '127.0.0.1'

        if not self.client_ip:
            # this is primarily for tests that sometimes don't have a remote_addr set on the request
            self.client_ip = '127.0.0.1'
        octets = self.client_ip.split('.')
        ip_chunk = '.'.join(octets[0:3])
        plain = '%d:%s:%s' % (
            timestamp, ip_chunk, tg.config.get('spinner_secret', 'abcdef'))
        return hashlib.sha1(six.ensure_binary(plain)).digest()

    @classmethod
    def validate_request(cls, request=None, now=None, params=None):
        if request is None:
            request = tg.request
        if params is None:
            params = request.params
        new_params = dict(params)
        if not request.method == 'GET':
            obj = None
            try:
                new_params.pop('timestamp', None)
                new_params.pop('spinner', None)
                obj = cls(request)
                expected_spinner = obj.make_spinner(obj.timestamp)
                if now is None:
                    now = time.time()
                if obj.timestamp > now + 5:
                    raise ValueError('Post from the future')
                if now - obj.timestamp > int(tg.config.get('spam.form_post_expiration', 24 * 60 * 60)):
                    raise ValueError('Post from the distant past')
                if obj.spinner != expected_spinner:
                    raise ValueError('Bad spinner value')
                for k in list(new_params.keys()):
                    try:
                        new_params[obj.dec(k)] = new_params[k]
                        new_params.pop(k)
                    except Exception as ex:
                        pass
                for fldno in range(obj.num_honey):
                    try:
                        value = new_params.pop('honey%s' % fldno)
                    except KeyError:
                        raise ValueError('Missing honeypot field: honey%s' % fldno)
                    if value:
                        raise ValueError('Value in honeypot field: %s' % value)
            except Exception as ex:
                attrs = dict(now=now, obj=vars(obj) if obj else None)
                log.info(f'Form validation failure: {attrs}')
                log.info('Error is', exc_info=ex)
                raise
        return new_params

    @classmethod
    def validate(cls, error_msg, error_url=None):
        '''Controller decorator to raise Invalid errors if bot protection is engaged'''
        def antispam_hook(remainder, params):
            '''Converts various errors in validate_request to a single Invalid message'''
            try:
                new_params = cls.validate_request(params=params)
                params.update(new_params)

                if tg.request.POST:
                    # request.params is immutable, but will reflect changes to request.POST
                    tg.request.POST.update(new_params)
            except (ValueError, TypeError, binascii.Error):
                testing = tg.request.environ.get('paste.testing', False)
                if testing and not tg.request.environ.get('regular_antispam_err_handling_even_when_tests'):
                    # re-raise so we can see problems more easily
                    raise
                else:
                    # regular antispam failure handling
                    tg.flash(error_msg, 'error')
                    redirect(error_url or six.ensure_text(tg.request.referer or '.'))
        return before_validate(antispam_hook)


class TruthyCallable:
    '''
    Wraps a callable to make it truthy in a boolean context.

    Assumes the callable returns a truthy value and can be called with no args.
    '''

    def __init__(self, callable):
        self.callable = callable

    def __call__(self, *args, **kw):
        return self.callable(*args, **kw)

    def __bool__(self):
        return self.callable()

    def __eq__(self, other):
        if other is True and bool(self):
            return True
        elif other is False and not bool(self):
            return True
        else:
            return NotImplemented


class TransformedDict(collections.MutableMapping):

    """
    A dictionary which applies an arbitrary
    key-altering function before accessing the keys.

    From: http://stackoverflow.com/questions/3387691/python-how-to-perfectly-override-a-dict
    """

    def __init__(self, *args, **kwargs):
        self.store = dict()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        return self.store[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __keytransform__(self, key):
        return key


class CaseInsensitiveDict(TransformedDict):

    def __keytransform__(self, key):
        return key.lower()


def postmortem_hook(etype, value, tb):  # pragma no cover
    import sys
    import pdb
    import traceback
    sys.stderr.write('Entering post-mortem PDB shell\n')
    traceback.print_exception(etype, value, tb)
    pdb.post_mortem(tb)


class LineAnchorCodeHtmlFormatter(HtmlFormatter):

    def _wrap_pre(self, inner):
        style = []
        if self.prestyles:
            style.append(self.prestyles)
        if self.noclasses:
            style.append('line-height: 125%')
        style = '; '.join(style)

        num = self.linenostart
        yield 0, ('<pre' + (style and ' style="%s"' % style) + '>')
        for tup in inner:
            yield (tup[0], f'<div id="l{num}" class="code_block">{tup[1]}</div>')
            num += 1
        yield 0, '</pre>'


def generate_code_stats(blob):
    from allura.lib import helpers as h

    stats = {'line_count': 0,
             'code_size': 0,
             'data_line_count': 0}
    code = h.really_unicode(blob.text)
    lines = code.split('\n')
    stats['code_size'] = blob.size
    stats['line_count'] = len(lines)
    spaces = re.compile(r'^\s*$')
    stats['data_line_count'] = sum(1 for l in lines if not spaces.match(l))
    return stats


def is_text_file(file):
    msg = magic.from_buffer(file[:1024])
    if ("text" in msg) or ("empty" in msg):
        return True
    return False


def take_while_true(source):
    x = source()
    while x:
        yield x
        x = source()


def serve_file(fp, filename, content_type, last_modified=None,
               cache_expires=None, size=None, embed=True, etag=None):
    '''Sets the response headers and serves as a wsgi iter'''
    if not etag and filename and last_modified:
        etag = f'{filename}?{last_modified}'.encode()
    if etag:
        etag_cache(etag)
    tg.response.headers['Content-Type'] = ''
    tg.response.content_type = str(content_type)
    tg.response.cache_expires = cache_expires or asint(
        tg.config.get('files_expires_header_secs', 60 * 60))
    tg.response.last_modified = last_modified
    if size:
        tg.response.content_length = size
    if 'Pragma' in tg.response.headers:
        del tg.response.headers['Pragma']
    if 'Cache-Control' in tg.response.headers:
        del tg.response.headers['Cache-Control']
    if not embed:
        from allura.lib import helpers as h
        tg.response.headers.add(
            'Content-Disposition',
            'attachment;filename="%s"' % h.urlquote(filename))
    # http://code.google.com/p/modwsgi/wiki/FileWrapperExtension
    block_size = 4096
    if 'wsgi.file_wrapper' in tg.request.environ:
        return tg.request.environ['wsgi.file_wrapper'](fp, block_size)
    else:
        return iter(lambda: fp.read(block_size), b'')


class ForgeHTMLSanitizerFilter(html5lib.filters.sanitizer.Filter):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # remove some elements from the sanitizer whitelist
        # <form> and <input> could be used for a social engineering attack to construct a form
        # others are just unexpected and confusing, and have no need to be used in markdown
        ns_html = html5lib.constants.namespaces['html']
        _form_elements = {(ns_html, 'button'),
                          (ns_html, 'datalist'),
                          (ns_html, 'fieldset'),
                          (ns_html, 'form'),
                          (ns_html, 'input'),
                          (ns_html, 'label'),
                          (ns_html, 'legend'),
                          (ns_html, 'meter'),
                          (ns_html, 'optgroup'),
                          (ns_html, 'option'),
                          (ns_html, 'output'),
                          (ns_html, 'progress'),
                          (ns_html, 'select'),
                          (ns_html, 'textarea'),
                          }
        _extra_allowed_elements = {
            (ns_html, 'summary'),
        }
        self.allowed_elements = (set(html5lib.filters.sanitizer.allowed_elements) | _extra_allowed_elements) - _form_elements

        # srcset is used in our own project_list/project_summary widgets
        # which are used as macros so go through markdown
        self.allowed_attributes = html5lib.filters.sanitizer.allowed_attributes | {(None, 'srcset')}

        self.valid_iframe_srcs = ('https://www.youtube.com/embed/',
                                  'https://www.youtube-nocookie.com/embed/',
                                  )
        self._prev_token_was_ok_iframe = False

    def sanitize_token(self, token):
        """
        Allow iframe tags if the src attribute matches our list of valid sources.
        Allow input tags if the type attribute matches "checkbox"
        Otherwise use default sanitization.
        """

        iframe_el = (html5lib.constants.namespaces['html'], 'iframe')
        self.allowed_elements.discard(iframe_el)
        ok_opening_iframe = False

        input_el = (html5lib.constants.namespaces['html'], 'input')
        self.allowed_elements.discard(input_el)

        if token.get('name') == 'iframe':
            attrs = token.get('data') or {}
            if attrs.get((None, 'src'), '').startswith(self.valid_iframe_srcs):
                self.allowed_elements.add(iframe_el)
                ok_opening_iframe = True
            elif token.get('type') == "EndTag" and self._prev_token_was_ok_iframe:
                self.allowed_elements.add(iframe_el)

        self._prev_token_was_ok_iframe = ok_opening_iframe

        if token.get('name') == 'input':
            attrs = token.get('data') or {}
            if attrs.get((None, 'type'), '') == "checkbox":
                self.allowed_elements.add(input_el)

        return super().sanitize_token(token)


def ip_address(request):
    ip = request.remote_addr
    if tg.config.get('ip_address_header'):
        ip = request.headers.get(tg.config['ip_address_header']) or ip
    return ip


class EmptyCursor(ODMCursor):
    """Ming cursor with no results"""

    def __init__(self, *args, **kw):
        pass

    @property
    def extensions(self):
        return []

    def count(self):
        return 0

    def _next_impl(self):
        raise StopIteration

    def next(self):
        raise StopIteration
    __next__ = next

    def options(self, **kw):
        return self

    def limit(self, limit):
        return self

    def skip(self, skip):
        return self

    def hint(self, index_or_name):
        return self

    def sort(self, *args, **kw):
        return self


class DateJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%dT%H:%M:%SZ')
        return json.JSONEncoder.default(self, obj)


def clean_phone_number(number):
    pattern = re.compile(r'\W+')
    number = pattern.sub('', number)
    return number


def phone_number_hash(number):
    number = clean_phone_number(number)
    return hashlib.sha1(number.encode('utf-8')).hexdigest()


@contextmanager
def skip_mod_date(model_cls):
    """ Avoids updating 'mod_date'

    Useful for saving cache on a model and things like that.

    .. note:: This only works when the changes made to the model are flushed.

    :Example:

    from allura import model as M
    key = self.can_merge_cache_key()
    with utils.skip_mod_date(M.MergeRequest):
        self.can_merge_cache[key] = val
        session(self).flush(self)

    :param model_cls: The model *class* being updated.
    """
    skip_mod_date = getattr(session(model_cls)._get(), 'skip_mod_date', False)
    session(model_cls)._get().skip_mod_date = True
    try:
        yield
    finally:
        session(model_cls)._get().skip_mod_date = skip_mod_date


@contextmanager
def skip_last_updated(model_cls):
    skip_last_updated = getattr(session(model_cls)._get(), 'skip_last_updated', False)
    session(model_cls)._get().skip_last_updated = True
    try:
        yield
    finally:
        session(model_cls)._get().skip_last_updated = skip_last_updated


def unique_attachments(attachments):
    """Given a list of :class:`allura.model.attachments.BaseAttachment` return
    a list where each filename present only once. If original list contains
    multiple attachmnets with the same filename the most recent one (i.e. with
    max :class:`bson.ObjectId`) will make it to the resulting list."""
    if not attachments:
        return []
    result = []
    # list passed to groupby should be sorted in order to avoid group key repetition
    attachments = sorted(attachments, key=op.attrgetter('filename'))
    for _, atts in groupby(attachments, op.attrgetter('filename')):
        result.append(max(atts, key=op.attrgetter('_id')))
    return result


def is_ajax(request):
    if request.headers.get('X-Requested-With', None) == 'XMLHttpRequest':
        return True
    return False


class JSONForExport(tg.jsonify.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__json__') and callable(obj.__json__):
            try:
                return obj.__json__(is_export=True)
            except TypeError:
                return obj.__json__()
        return super().default(obj)


@contextmanager
def umask(new_mask):
    cur_mask = os.umask(new_mask)
    try:
        yield
    finally:
        os.umask(cur_mask)


def get_reaction_emoji_list():
    """ Get reactions emoji list from .ini file. If not defined there get fixed
    default emoji list """
    emo_list = tg.config.get('reactions.emoji_list')
    if emo_list is None:
        emo_list = [':+1:', ':-1:', ':smile:', ':tada:', ':confused:', ':heart:']
    else:
        emo_list = emo_list.split(',')
    return emo_list


def get_reactions_json():
    """ Returns global reactions json """
    j = OrderedDict()
    for em in get_reaction_emoji_list():
        j[em] = emoji.emojize(em, language='alias')
    return json.dumps(j)


def get_usernames_from_md(text):
    """ Returns a unique usernames set from a text """
    usernames = set()
    html_text = g.markdown.convert(text)
    soup = BeautifulSoup(html_text, 'html.parser')
    for mention in soup.select('a.user-mention'):
        usernames.add(mention.get_text().replace('@', ''))
    return usernames


def get_key_from_value(d, val):
    """ Get key from given value. return empty str if not exists """
    for k, v in d.items():
        if val in v:
            return k
    return ''


def is_nofollow_url(url):
    url_domain = urlparse(url).hostname
    ok_domains = re.split(r'\s*,\s*', tg.config.get('nofollow_exempt_domains', '')) + [tg.config['domain']]
    return url_domain and url_domain not in ok_domains


def smart_str(s):
    '''
    Returns a bytestring version of 's' from any type
    '''
    if isinstance(s, bytes):
        return s
    else:
        return str(s).encode('utf-8')


def generate_smart_str(params):
    if isinstance(params, collections.Mapping):
        params_list = params.items()
    else:
        params_list = params
    for key, value in params_list:
        yield smart_str(key), smart_str(value)


def urlencode(params):
    """
    A version of Python's urllib.urlencode() function that can operate on
    unicode strings. The parameters are first case to UTF-8 encoded strings and
    then encoded as per normal.
    """
    return six.moves.urllib.parse.urlencode([i for i in generate_smart_str(params)])


def close_ipv4_addrs(ip1, ip2):
    return ip1.split('.')[0:3] == ip2.split('.')[0:3]


@contextmanager
def socket_default_timeout(timeout):
    orig_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        yield
    finally:
        socket.setdefaulttimeout(orig_timeout)
