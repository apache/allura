# -*- coding: utf-8 -*-
import os
import os.path
import difflib
import urllib
import re
import json
import logging
import cPickle as pickle
from hashlib import sha1
from datetime import datetime, timedelta

import tg
import genshi.template
import chardet
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from formencode.validators import FancyValidator
from dateutil.parser import parse
from bson import ObjectId
from pymongo.errors import InvalidId
from contextlib import contextmanager
from pylons import c, response, request
from tg.decorators import before_validate
from formencode.variabledecode import variable_decode
import formencode
from jinja2 import Markup
from paste.deploy.converters import asbool

from webhelpers import date, feedgenerator, html, number, misc, text

from allura.lib import exceptions as exc
# Reimport to make available to templates
from allura.lib.decorators import exceptionless
from allura.lib import AsciiDammit
from .security import has_access

re_path_portion_fragment = re.compile(r'[a-z][-a-z0-9]{2,}')
re_path_portion = re.compile(r'^[a-z][-a-z0-9]{2,}$')
re_clean_vardec_key = re.compile(r'''\A
( # first part
\w+# name...
(-\d+)?# with optional -digits suffix
)
(\. # next part(s)
\w+# name...
(-\d+)?# with optional -digits suffix
)+
\Z''', re.VERBOSE)

def make_safe_path_portion(ustr):
    ustr = really_unicode(ustr)
    s = ustr.encode('latin-1', 'ignore')
    s = AsciiDammit.asciiDammit(s)
    s = s.lower()
    s = '-'.join(re_path_portion_fragment.findall(s))
    s = s.replace('--', '-')
    return s

def monkeypatch(*objs):
    def patchem(func):
        for obj in objs:
            setattr(obj, func.__name__, func)
    return patchem

def urlquote(url, safe="/"):
    try:
        return urllib.quote(str(url), safe=safe)
    except UnicodeEncodeError:
        return urllib.quote(url.encode('utf-8'), safe=safe)

def urlquoteplus(url, safe=""):
    try:
        return urllib.quote_plus(str(url), safe=safe)
    except UnicodeEncodeError:
        return urllib.quote_plus(url.encode('utf-8'), safe=safe)

def really_unicode(s):
    if s is None: return u''
    # try naive conversion to unicode
    try:
        return unicode(s)
    except UnicodeDecodeError:
        pass
    # Try to guess the encoding
    encodings = [
        lambda:'utf-8',
        lambda:chardet.detect(s[:1024])['encoding'],
        lambda:chardet.detect(s)['encoding'],
        lambda:'latin-1',
        ]
    for enc in encodings:
        try:
            return unicode(s, enc())
        except UnicodeDecodeError:
            pass
    # Return the repr of the str -- should always be safe
    return unicode(repr(str(s)))[1:-1]

def find_project(url_path):
    from allura import model as M
    for n in M.Neighborhood.query.find():
        if url_path.strip("/").startswith(n.url_prefix.strip("/")):
            break
    else:
        return None, url_path
    project_part = n.shortname_prefix + url_path[len(n.url_prefix):] # easily off-by-one, might be better to join together everything but url_prefix
    parts = project_part.split('/')
    length = len(parts)
    while length:
        shortname = '/'.join(parts[:length])
        p = M.Project.query.get(shortname=shortname, deleted=False,
                                neighborhood_id=n._id)
        if p: return p, parts[length:]
        length -= 1
    return None, url_path.split('/')

def find_executable(exe_name):
    '''Find the abspath of a given executable (which
    must be on the PATH)'''
    for dirname in os.environ['PATH'].split(os.pathsep):
        path = os.path.join(dirname, exe_name)
        if os.access(path, os.X_OK): return path

def make_neighborhoods(ids):
    return _make_xs('Neighborhood', ids)

def make_projects(ids):
    return _make_xs('Project', ids)

def make_users(ids):
    return _make_xs('User', ids)

def make_roles(ids):
    return _make_xs('ProjectRole', ids)

def _make_xs(X, ids):
    from allura import model as M
    X = getattr(M, X)
    ids = list(ids)
    results = dict(
        (r._id, r)
        for r in X.query.find(dict(_id={'$in':ids})))
    result = (results.get(i) for i in ids)
    return (r for r in result if r is not None)

@contextmanager
def push_config(obj, **kw):
    saved_attrs = {}
    new_attrs = []
    for k, v in kw.iteritems():
        try:
            saved_attrs[k] = getattr(obj, k)
        except AttributeError:
            new_attrs.append(k)
        setattr(obj, k, v)
    try:
        yield obj
    finally:
        for k, v in saved_attrs.iteritems():
            setattr(obj, k, v)
        for k in new_attrs:
            delattr(obj, k)

def sharded_path(name, num_parts=2):
    parts = [
        name[:i + 1]
        for i in range(num_parts) ]
    return '/'.join(parts)

def set_context(project_shortname_or_id, mount_point=None, app_config_id=None, neighborhood=None):
    from allura import model
    try:
        p = model.Project.query.get(_id=ObjectId(str(project_shortname_or_id)))
    except InvalidId:
        p = None
    if p is None and type(project_shortname_or_id) != ObjectId:
        if neighborhood is None:
            raise TypeError('neighborhood is required; it must not be None')
        if not isinstance(neighborhood, model.Neighborhood):
            n = model.Neighborhood.query.get(name=neighborhood)
            if n is None:
                try:
                    n = model.Neighborhood.query.get(_id=ObjectId(str(neighborhood)))
                except InvalidId:
                    pass
            if n is None:
                raise exc.NoSuchNeighborhoodError("Couldn't find neighborhood %s" %
                                      repr(neighborhood))
            neighborhood = n

        query = dict(shortname=project_shortname_or_id, neighborhood_id=neighborhood._id)
        p = model.Project.query.get(**query)
    if p is None:
        raise exc.NoSuchProjectError("Couldn't find project %s nbhd %s" %
                                 (project_shortname_or_id, neighborhood))
    c.project = p

    if app_config_id is None:
        c.app = p.app_instance(mount_point)
    else:
        if isinstance(app_config_id, basestring):
            app_config_id = ObjectId(app_config_id)
        app_config = model.AppConfig.query.get(_id=app_config_id)
        c.app = p.app_instance(app_config)

@contextmanager
def push_context(project_id, mount_point=None, app_config_id=None, neighborhood=None):
    project = getattr(c, 'project', ())
    app = getattr(c, 'app', ())
    set_context(project_id, mount_point, app_config_id, neighborhood)
    try:
        yield
    finally:
        if project == ():
            del c.project
        else:
            c.project = project
        if app == ():
            del c.app
        else:
            c.app = app

def encode_keys(d):
    '''Encodes the unicode keys of d, making the result
    a valid kwargs argument'''
    return dict(
        (k.encode('utf-8'), v)
        for k, v in d.iteritems())

def vardec(fun):
    def vardec_hook(remainder, params):
        new_params = variable_decode(dict(
                (k, v) for k, v in params.items()
                if re_clean_vardec_key.match(k)))
        params.update(new_params)
    before_validate(vardec_hook)(fun)
    return fun

def nonce(length=4):
    return sha1(ObjectId().binary + os.urandom(10)).hexdigest()[:length]

def cryptographic_nonce(length=40):
    hex_format = '%.2x' * length
    return hex_format % tuple(map(ord, os.urandom(length)))

def ago(start_time):
    """
    Return time since starting time as a rounded, human readable string.
    E.g., "3 hours ago"
    """

    if start_time is None: return 'unknown'
    granularities = ['century', 'decade', 'year', 'month', 'day', 'hour',
                     'minute']
    end_time = datetime.utcnow()
    if end_time - start_time > timedelta(days=7):
        return start_time.strftime('%Y-%m-%d')

    while True:
        granularity = granularities.pop()
        ago = date.distance_of_time_in_words(
            start_time, end_time, granularity, round=True)
        rounded_to_one_granularity = 'and' not in ago
        if rounded_to_one_granularity:
            break
    return ago + ' ago'

def ago_ts(timestamp):
    return ago(datetime.utcfromtimestamp(timestamp))

class DateTimeConverter(FancyValidator):

    def _to_python(self, value, state):
        try:
            return parse(value)
        except ValueError:
            if self.if_invalid != formencode.api.NoDefault:
                return self.if_invalid
            else:
                raise


    def _from_python(self, value, state):
        return value.isoformat()

def absurl(url):
    if url is None: return None
    if '://' in url: return url
    return request.scheme + '://' + request.host + url

def diff_text(t1, t2, differ=None):
    t1_lines = t1.replace('\r', '').split('\n')
    t2_lines = t2.replace('\r', '').split('\n')
    t1_words = []
    for line in t1_lines:
        for word in line.split(' '):
            t1_words.append(word)
            t1_words.append(' ')
        t1_words.append('\n')
    t2_words = []
    for line in t2_lines:
        for word in line.split(' '):
            t2_words.append(word)
            t2_words.append(' ')
        t2_words.append('\n')
    if differ is None:
        differ = difflib.SequenceMatcher(None, t1_words, t2_words)
    result = []
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag in ('delete', 'replace'):
            result += [ '<del>' ] + t1_words[i1:i2] + [ '</del>' ]
        if tag in ('insert', 'replace'):
            result += [ '<ins>' ] + t2_words[j1:j2] + [ '</ins>' ]
        if tag == 'equal':
            result += t1_words[i1:i2]
    return ' '.join(result).replace('\n', '<br/>\n')

def gen_message_id():
    if getattr(c, 'project', None):
        parts = c.project.url().split('/')[1:-1]
    else:
        parts = ['mail']
    if getattr(c, 'app', None):
        addr = '%s.%s' % (nonce(40), c.app.config.options['mount_point'])
    else:
        addr = nonce(40)
    return '%s@%s.sourceforge.net' % (
        addr, '.'.join(reversed(parts)))

class ProxiedAttrMeta(type):
    def __init__(cls, name, bases, dct):
        for v in dct.itervalues():
            if isinstance(v, attrproxy):
                v.cls = cls

class attrproxy(object):
    cls = None
    def __init__(self, *attrs):
        self.attrs = attrs

    def __repr__(self):
        return '<attrproxy on %s for %s>' % (
            self.cls, self.attrs)

    def __get__(self, obj, klass=None):
        if obj is None:
            obj = klass
        for a in self.attrs:
            obj = getattr(obj, a)
        return proxy(obj)

    def __getattr__(self, name):
        if self.cls is None:
            return promised_attrproxy(lambda:self.cls, name)
        return getattr(
            attrproxy(self.cls, *self.attrs),
            name)

class promised_attrproxy(attrproxy):
    def __init__(self, promise, *attrs):
        super(promised_attrproxy, self).__init__(*attrs)
        self._promise = promise

    def __repr__(self):
        return '<promised_attrproxy for %s>' % (self.attrs,)

    def __getattr__(self, name):
        cls = self._promise()
        return getattr(cls, name)

class proxy(object):
    def __init__(self, obj):
        self._obj = obj
    def __getattr__(self, name):
        return getattr(self._obj, name)
    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)

def render_genshi_plaintext(template_name, **template_vars):
    assert os.path.exists(template_name)
    fd = open(template_name)
    try:
        tpl_text = fd.read()
    finally:
        fd.close()
    filepath = os.path.dirname(template_name)
    tt = genshi.template.NewTextTemplate(tpl_text,
            filepath=filepath, filename=template_name)
    stream = tt.generate(**template_vars)
    return stream.render(encoding='utf-8').decode('utf-8')

site_url = None # cannot set it just yet since tg.config is empty

def full_url(url):
    """Make absolute URL from the relative one.
    """
    global site_url
    if site_url is None:
        # XXX: add a separate tg option instead of re-using openid.realm
        site_url = tg.config.get('openid.realm', 'https://newforge.sf.geek.net/')
        site_url = site_url.replace('https:', 'http:')
        if not site_url.endswith('/'):
            site_url += '/'
    if url.startswith('/'):
        url = url[1:]
    return site_url + url

@tg.expose(content_type='text/plain')
def json_validation_error(controller, **kwargs):
    result = dict(status='Validation Error',
                errors=c.validation_exception.unpack_errors(),
                value=c.validation_exception.value,
                params=kwargs)
    response.status = 400
    return json.dumps(result, indent=2)

def pop_user_notifications(user=None):
    from allura import model as M
    if user is None: user = c.user
    mbox = M.Mailbox.query.get(user_id=user._id, is_flash=True)
    if mbox:
        notifications = M.Notification.query.find(dict(_id={'$in':mbox.queue}))
        mbox.queue = []
        for n in notifications: yield n

def config_with_prefix(d, prefix):
    '''Return a subdictionary keys with a given prefix,
    with the prefix stripped
    '''
    plen = len(prefix)
    return dict((k[plen:], v) for k, v in d.iteritems()
                if k.startswith(prefix))

@contextmanager
def twophase_transaction(*engines):
    connections = [
        e.contextual_connect()
        for e in engines ]
    txns = []
    to_rollback = []
    try:
        for c in connections:
            txn = c.begin_twophase()
            txns.append(txn)
            to_rollback.append(txn)
        yield
        to_rollback = []
        for txn in txns:
            txn.prepare()
            to_rollback.append(txn)
        for txn in txns:
            txn.commit()
    except:
        for txn in to_rollback:
            txn.rollback()
        raise

class log_action(object):
    extra_proto = dict(
        action=None,
        action_type=None,
        tool_type=None,
        tool_mount=None,
        project=None,
        neighborhood=None,
        username=None,
        url=None,
        ip_address=None)

    def __init__(self, logger, action):
        self._logger = logger
        self._action = action

    def log(self, level, message, *args, **kwargs):
        kwargs = dict(kwargs)
        extra = kwargs.setdefault('extra', {})
        meta = kwargs.pop('meta', {})
        kwpairs = extra.setdefault('kwpairs', {})
        for k, v in meta.iteritems():
            kwpairs['meta_%s' % k] = v
        extra.update(self._make_extra())
        self._logger.log(level, self._action + ': ' + message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self.log(logging.INFO, message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.log(logging.DEBUG, message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.log(logging.ERROR, message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self.log(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self.log(logging.EXCEPTION, message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.log(logging.EXCEPTION, message, *args, **kwargs)
    warn = warning

    def _make_extra(self):
        result = dict(self.extra_proto, action=self._action)
        try:
            if hasattr(c, 'app') and c.app:
                result['tool_type'] = c.app.config.tool_name
                result['tool_mount'] = c.app.config.options['mount_point']
            if hasattr(c, 'project') and c.project:
                result['project'] = c.project.shortname
                result['neighborhood'] = c.project.neighborhood.name
            if hasattr(c, 'user') and c.user:
                result['username'] = c.user.username
            else:
                result['username'] = '*system'
            try:
                result['url'] = request.url
                ip_address = request.headers.get('X_FORWARDED_FOR', request.remote_addr)
                if ip_address is not None:
                    ip_address = ip_address.split(',')[0].strip()
                    result['ip_address'] = ip_address
                else:
                    result['ip_address'] = '0.0.0.0'
            except TypeError:
                pass
            return result
        except:
            self._logger.warning('Error logging to rtstats, some info may be missing', exc_info=True)
            return result

def paging_sanitizer(limit, page, total_count, zero_based_pages=True):
    """Return limit, page - both converted to int and constrained to
    valid ranges based on total_count.

    Useful for sanitizing limit and page query params.
    """
    limit = max(int(limit), 1)
    max_page = (total_count / limit) + (1 if total_count % limit else 0)
    max_page = max(0, max_page - (1 if zero_based_pages else 0))
    page = min(max(int(page), (0 if zero_based_pages else 1)), max_page)
    return limit, page


def _add_inline_line_numbers_to_text(text):
    markup_text = '<div class="codehilite"><pre>'
    for line_num, line in enumerate(text.splitlines(), 1):
        markup_text = markup_text + '<span id="l%s" class="code_block"><span class="lineno">%s</span> %s</span>' % (line_num, line_num, line)
    markup_text = markup_text + '</pre></div>'
    return markup_text


def _add_table_line_numbers_to_text(text):
    def _prepend_whitespaces(num, max_num):
        num, max_num = str(num), str(max_num)
        diff = len(max_num) - len(num)
        return ' ' * diff + num

    def _len_to_str_column(l, start=1):
        max_num = l + start
        return '\n'.join(map(_prepend_whitespaces, range(start, max_num), [max_num] * l))

    lines = text.splitlines(True)
    linenumbers = '<td class="linenos"><div class="linenodiv"><pre>' + _len_to_str_column(len(lines)) + '</pre></div></td>'
    markup_text = '<table class="codehilitetable"><tbody><tr>' + linenumbers + '<td class="code"><div class="codehilite"><pre>'
    for line_num, line in enumerate(lines, 1):
        markup_text = markup_text + '<span id="l%s" class="code_block">%s</span>' % (line_num, line)
    markup_text = markup_text + '</pre></div></td></tbody></table>'
    return markup_text


INLINE = 'inline'
TABLE = 'table'
def render_any_markup(name, text, code_mode=False, linenumbers_style=TABLE):
    """
    renders any markup format using the pypeline
    Returns jinja-safe text
    """
    if text == '':
        text = '<p><em>Empty File</em></p>'
    else:
        text = pylons.g.pypeline_markup.render(name, text)
        if not pylons.g.pypeline_markup.can_render(name):
            if code_mode and linenumbers_style == INLINE:
                text = _add_inline_line_numbers_to_text(text)
            elif code_mode and linenumbers_style == TABLE:
                text = _add_table_line_numbers_to_text(text)
            else:
                text = '<pre>%s</pre>' % text
    return Markup(text)
