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
import base64
import sys
import os
import os.path
import difflib
import jinja2

import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
import re
import unicodedata
import json
import logging
import string
import random
import six.moves.cPickle as pickle
from hashlib import sha1
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
import shlex
import socket
from functools import partial
from io import BytesIO
import cgi

import emoji
import tg
import six
import cchardet as chardet
import pkg_resources
from formencode.validators import FancyValidator
from dateutil.parser import parse
from bson import ObjectId
from paste.deploy import appconfig
from pymongo.errors import InvalidId
from contextlib import contextmanager
from tg import tmpl_context as c, app_globals as g
from tg import response, request
from tg.decorators import before_validate
from formencode.variabledecode import variable_decode
import formencode
from markupsafe import Markup
from jinja2.filters import escape, do_filesizeformat
from jinja2.utils import pass_context, htmlsafe_json_dumps
from paste.deploy.converters import asbool, aslist, asint
from webhelpers2 import date, text
from webob.exc import HTTPUnauthorized

from allura.lib import exceptions as exc
from allura.lib import utils
import urllib.parse as urlparse
from urllib.parse import urlencode
import math
from webob.multidict import MultiDict

# import to make available to templates, don't delete:
from .security import has_access, is_allowed_by_role, is_site_admin


log = logging.getLogger(__name__)

# http://stackoverflow.com/questions/2063213/regular-expression-for-validating-dns-label-host-name
# modified to remove capital A-Z and make length parameterized
# and not use lookbehind assertion since JS doesn't support that
dns_var_length = r'^(?![0-9]+$)(?!-)[a-z0-9-]{%s}[a-z0-9]$'

# project & tool names must comply to DNS since used in subdomains for emailing
re_mount_points = {
    're_project_name': dns_var_length % '2,14',  # validates project, subproject, and user names
    're_tool_mount_point': dns_var_length % '0,62',  # validates tool mount point names
    're_tool_mount_point_fragment': r'[a-z][-a-z0-9]*',
    're_relaxed_tool_mount_point': r'^[a-zA-Z0-9][-a-zA-Z0-9_\.\+]{0,62}$',
    're_relaxed_tool_mount_point_fragment':  r'[a-zA-Z0-9][-a-zA-Z0-9_\.\+]*'
}
# validates project, subproject, and user names
re_project_name = re.compile(re_mount_points['re_project_name'])

# validates tool mount point names
re_tool_mount_point = re.compile(re_mount_points['re_tool_mount_point'])
re_tool_mount_point_fragment = re.compile(re_mount_points['re_tool_mount_point_fragment'])
re_relaxed_tool_mount_point = re.compile(re_mount_points['re_relaxed_tool_mount_point'])
re_relaxed_tool_mount_point_fragment = re.compile(re_mount_points['re_relaxed_tool_mount_point_fragment'])

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

# markdown escaping regexps
re_amp = re.compile(r'''
    [&]          # amp
    (?=          # look ahead for:
      ([a-zA-Z0-9]+;)  # named HTML entity
      |
      (\#[0-9]+;)      # decimal entity
      |
      (\#x[0-9A-F]+;)  # hex entity
    )
    ''', re.VERBOSE)
re_leading_spaces = re.compile(r'^[\t ]+', re.MULTILINE)
re_preserve_spaces = re.compile(r'''
    [ ]           # space
    (?=[ ])       # lookahead for a space
    ''', re.VERBOSE)
re_angle_bracket_open = re.compile('<')
re_angle_bracket_close = re.compile('>')
md_chars_matcher_all = re.compile(r"([`\*_{}\[\]\(\)#!\\\.+-])")


def make_safe_path_portion(ustr, relaxed=True):
    """Return an ascii representation of ``ustr`` that conforms to mount point
    naming :attr:`rules <re_tool_mount_point_fragment>`.

    Will return an empty string if no char in ``ustr`` is ascii-encodable.

    :param relaxed: Use relaxed mount point naming rules (allows more
        characters. See :attr:`re_relaxed_tool_mount_point_fragment`.
    :returns: The converted string.

    """
    regex = (re_relaxed_tool_mount_point_fragment if relaxed else
             re_tool_mount_point_fragment)
    ustr = really_unicode(ustr)
    s = ustr.encode('ascii', 'ignore')
    s = six.ensure_text(s)
    if not relaxed:
        s = s.lower()
    s = '-'.join(regex.findall(s))
    s = s.replace('--', '-')
    return s


def escape_json(data) -> str:
    # Templates should use `|tojson` instead of this
    return str(htmlsafe_json_dumps(data))  # str() to keep previous behavior of being str, not MarkupSafe


def querystring(request, url_params):
    """
    add/update/remove url parameters. When a value is set to None the key will
    be removed from the final constructed url.

    :param request: request object
    :param url_params: dict with the params that should be updated/added/deleted.
    :return: a full url with updated url parameters.
    """
    params = urlparse.parse_qs(request.query_string)
    params.update(url_params)
    for param in list(params.keys()):
        if params[param] is None:
            del params[param]
    # flatten dict values
    params = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}
    url_parts = urlparse.urlparse(request.url)
    url = url_parts._replace(query=urlencode(params)).geturl()
    return url


def ceil(number):
    return math.ceil(number)


def strip_bad_unicode(s):
    """
    xml doesn't like some control characters: https://www.w3.org/TR/REC-xml/#charsets
    :param s:
    :return:
    """
    return re.sub('[\x00-\x08\x0B\x0C\x0E-\x1F]', '', s)


def monkeypatch(*objs):
    def patchem(func):
        for obj in objs:
            setattr(obj, func.__name__, func)
    return patchem


def urlquote(url, safe=b"/"):
    try:
        return six.moves.urllib.parse.quote(str(url), safe=safe)
    except UnicodeEncodeError:
        return six.moves.urllib.parse.quote(url.encode('utf-8'), safe=safe)


def urlquoteplus(url, safe=b""):
    try:
        return six.moves.urllib.parse.quote_plus(str(url), safe=safe)
    except UnicodeEncodeError:
        return six.moves.urllib.parse.quote_plus(url.encode('utf-8'), safe=safe)


def urlquote_path_only(url):
    """
    Given a relative url like /fö/bar/?sdf&sdf
    urlquote only the path portion of it, leaving any querystring or target hash unquoted
    :param url:
    :return:
    """
    if '?' in url:
        url_path, url_joiner, url_remainder = url.partition('?')
    elif '#' in url:
        url_path, url_joiner, url_remainder = url.partition('#')
    else:
        url_path = url
        url_joiner = url_remainder = ''
    return urlquote(url_path) + url_joiner + url_remainder


def _attempt_encodings(s, encodings):
    if s is None:
        return ''
    for enc in encodings:
        try:
            if enc is None:
                if six.PY3 and isinstance(s, bytes):
                    # special handling for bytes (avoid b'asdf' turning into "b'asfd'")
                    return s.decode('utf-8')
                return str(s)  # try default encoding, and handle other types like int, etc
            else:
                return str(s, enc)
        except (UnicodeDecodeError, LookupError):
            pass
    # Return the repr of the str -- should always be safe
    return str(repr(str(s)))[1:-1]


def really_unicode(s):
    if isinstance(s, str):
        # default case.  Also lets Markup() instances be preserved
        return s
    # Try to guess the encoding

    def encodings():
        yield None
        yield 'utf-8'
        yield chardet.detect(s[:1024])['encoding']
        yield chardet.detect(s)['encoding']
        yield 'latin-1'
    return _attempt_encodings(s, encodings())


def find_user(email):
    from allura import model as M
    return M.User.by_email_address(email)


def find_project(url_path):
    from allura import model as M
    for n in M.Neighborhood.query.find():
        if url_path.strip("/").startswith(n.url_prefix.strip("/")):
            break
    else:
        return None, url_path
    # easily off-by-one, might be better to join together everything but
    # url_prefix
    project_part = n.shortname_prefix + url_path[len(n.url_prefix):]
    parts = project_part.split('/')
    length = len(parts)
    while length:
        shortname = '/'.join(parts[:length])
        p = M.Project.query.get(shortname=shortname, deleted=False,
                                neighborhood_id=n._id)
        if p:
            return p, parts[length:]
        length -= 1
    return None, url_path.split('/')


def make_neighborhoods(ids):
    return _make_xs('Neighborhood', ids)


def make_roles(ids):
    return _make_xs('ProjectRole', ids)


def _make_xs(X, ids):
    from allura import model as M
    X = getattr(M, X)
    ids = list(ids)
    results = {
        r._id: r
        for r in X.query.find(dict(_id={'$in': ids}))}
    result = (results.get(i) for i in ids)
    return (r for r in result if r is not None)


def make_app_admin_only(app):
    from allura.model.auth import ProjectRole
    admin_role = ProjectRole.by_name('Admin', app.project)
    for ace in [ace for ace in app.acl if ace.role_id != admin_role._id]:
        app.acl.remove(ace)


@contextmanager
def push_config(obj, **kw):
    # if you need similar for a dict, use mock.patch.dict

    saved_attrs = {}
    new_attrs = []
    for k, v in kw.items():
        try:
            saved_attrs[k] = getattr(obj, k)
        except AttributeError:
            new_attrs.append(k)
        setattr(obj, k, v)
    try:
        yield obj
    finally:
        for k, v in saved_attrs.items():
            setattr(obj, k, v)
        for k in new_attrs:
            delattr(obj, k)


def sharded_path(name, num_parts=2):
    parts = [
        name[:i + 1]
        for i in range(num_parts)]
    return '/'.join(parts)


def set_context(project_shortname_or_id, mount_point=None, app_config_id=None, neighborhood=None):
    """
    Set ``c.project`` and ``c.app`` globals

    :param project_id: _id or shortname of a project
    :type project_id: ObjectId|str
    :param mount_point: mount point to set c.app by
    :type mount_point: str
    :param app_config_id: alternative to mount_point parameter
    :type app_config_id: ObjectId|str
    :param neighborhood: neighborhood full name, required if project is specified by shortname
    :type neighborhood: str
    """
    from allura import model
    try:
        p = model.Project.query.get(_id=ObjectId(str(project_shortname_or_id)))
    except InvalidId:
        p = None
    if p is None and not isinstance(project_shortname_or_id, ObjectId):
        if neighborhood is None:
            raise TypeError('neighborhood is required; it must not be None')
        if not isinstance(neighborhood, model.Neighborhood):
            n = model.Neighborhood.query.get(name=neighborhood)
            if n is None:
                try:
                    n = model.Neighborhood.query.get(
                        _id=ObjectId(str(neighborhood)))
                except InvalidId:
                    pass
            if n is None:
                raise exc.NoSuchNeighborhoodError(
                    "Couldn't find neighborhood %s" %
                    repr(neighborhood))
            neighborhood = n

        query = dict(shortname=project_shortname_or_id,
                     neighborhood_id=neighborhood._id)
        p = model.Project.query.get(**query)
    if p is None:
        raise exc.NoSuchProjectError("Couldn't find project %s nbhd %s" %
                                     (project_shortname_or_id, neighborhood))
    c.project = p

    if app_config_id is None:
        c.app = p.app_instance(mount_point)
    else:
        if isinstance(app_config_id, str):
            app_config_id = ObjectId(app_config_id)
        app_config = model.AppConfig.query.get(_id=app_config_id)
        c.app = p.app_instance(app_config)


@contextmanager
def push_context(project_id, mount_point=None, app_config_id=None, neighborhood=None):
    """
    A context manager to set ``c.project`` and ``c.app`` globals temporarily.
    To set ``c.user`` or others, use ``push_config(c, user=...)``

    :param project_id: _id or shortname of a project
    :type project_id: ObjectId|str
    :param mount_point: mount point to set c.app by
    :type mount_point: str
    :param app_config_id: alternative to mount_point parameter
    :type app_config_id: ObjectId|str
    :param neighborhood: neighborhood full name, required if project is specified by shortname
    :type neighborhood: str
    """
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
    return {
        six.ensure_str(k): v
        for k, v in d.items()}


def vardec(fun):
    def vardec_hook(remainder, params):
        new_params = variable_decode({
            k: v for k, v in params.items()
            if re_clean_vardec_key.match(k)})
        params.update(new_params)
    before_validate(vardec_hook)(fun)
    return fun


def convert_bools(conf, prefix=''):
    '''
    For a given dict, automatically convert any true/false string values into bools.
    Only applies to keys starting with the prefix.

    :param dict conf:
    :param str prefix:
    :return: dict
    '''
    def convert_value(val):
        if isinstance(val, str):
            if val.strip().lower() == 'true':
                return True
            elif val.strip().lower() == 'false':
                return False
        return val

    return {
        k: (convert_value(v) if k.startswith(prefix) else v)
        for k, v in conf.items()
    }


def nonce(length=4):
    return sha1(ObjectId().binary + os.urandom(10)).hexdigest()[:length]


def cryptographic_nonce(length=40):
    rand_bytes = os.urandom(length)
    rand_ints = tuple(rand_bytes)
    hex_format = '%.2x' * length
    return hex_format % rand_ints


def random_password(length=20, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(length))


def ago(start_time, show_date_after=7):
    """
    Return time since starting time as a rounded, human readable string.
    E.g., "3 hours ago"
    Also works with future times
    E.g., "in 3 hours"
    """

    if start_time is None:
        return 'unknown'
    granularities = ['century', 'decade', 'year', 'month', 'day', 'hour', 'minute', 'second']
    end_time = datetime.utcnow()
    if show_date_after is not None and abs(end_time - start_time) > timedelta(days=show_date_after):
        return start_time.strftime('%Y-%m-%d')

    while True:
        granularity = granularities.pop()
        ago = date.distance_of_time_in_words(start_time, end_time, granularity, round=True)
        rounded_to_one_granularity = 'and' not in ago
        if rounded_to_one_granularity:
            break

    if (end_time - start_time).total_seconds() >= 0:
        return ago + ' ago'
    else:
        return 'in ' + ago


def ago_ts(timestamp):
    return ago(datetime.utcfromtimestamp(timestamp))


def ago_string(s):
    try:
        return ago(parse(s, ignoretz=True))
    except (ValueError, AttributeError, TypeError):
        return 'unknown'


class DateTimeConverter(FancyValidator):

    def _to_python(self, value, state):
        try:
            return parse(value)
        except (ValueError, TypeError):
            if self.if_invalid != formencode.api.NoDefault:
                return self.if_invalid
            else:
                raise

    def _from_python(self, value, state):
        return value.isoformat()


def absurl(url):
    """
    Given a root-relative URL, return a full URL including protocol and host
    """
    if url is None:
        return None
    if '://' in url:
        return url
    host = tg.config['base_url'].rstrip('/')
    return host + url


def diff_text(t1, t2, differ=None):
    t1_lines = t1.replace('\r', '').split('\n')
    t2_lines = t2.replace('\r', '').split('\n')
    t1_words = []
    for line in t1_lines:
        for word in line.split(' '):
            t1_words.append(word)
        t1_words.append('\n')
    t2_words = []
    for line in t2_lines:
        for word in line.split(' '):
            t2_words.append(word)
        t2_words.append('\n')
    if differ is None:
        differ = difflib.SequenceMatcher(None, t1_words, t2_words)
    result = []

    def escape_list(words_list):
        return [cgi.escape(words) for words in words_list]

    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag in ('delete', 'replace'):
            result += ['<del>'] + escape_list(t1_words[i1:i2]) + ['</del>']
        if tag in ('insert', 'replace'):
            result += ['<ins>'] + escape_list(t2_words[j1:j2]) + ['</ins>']
        if tag == 'equal':
            result += escape_list(t1_words[i1:i2])
    return Markup(' '.join(result).replace('\n', '<br/>\n'))


def gen_message_id(_id=None):
    if not _id:
        _id = nonce(40)
    if getattr(c, 'project', None):
        parts = c.project.url().split('/')[1:-1]
    else:
        parts = ['mail']
    if getattr(c, 'app', None):
        addr = '{}.{}'.format(_id, c.app.config.options['mount_point'])
    else:
        addr = _id
    return '{}@{}.{}'.format(
        addr, '.'.join(reversed(parts)), tg.config['domain'])


class ProxiedAttrMeta(type):

    def __init__(cls, name, bases, dct):
        for v in dct.values():
            if isinstance(v, attrproxy):
                v.cls = cls


class attrproxy:
    cls = None

    def __init__(self, *attrs):
        self.attrs = attrs

    def __repr__(self):
        return '<attrproxy on {} for {}>'.format(
            self.cls, self.attrs)

    def __get__(self, obj, klass=None):
        if obj is None:
            obj = klass
        for a in self.attrs:
            obj = getattr(obj, a)
        return proxy(obj)

    def __getattr__(self, name):
        if self.cls is None:
            return promised_attrproxy(lambda: self.cls, name)
        return getattr(
            attrproxy(self.cls, *self.attrs),
            name)


class promised_attrproxy(attrproxy):

    def __init__(self, promise, *attrs):
        super().__init__(*attrs)
        self._promise = promise

    def __repr__(self):
        return f'<promised_attrproxy for {self.attrs}>'

    def __getattr__(self, name):
        cls = self._promise()
        return getattr(cls, name)


class proxy:

    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return getattr(self._obj, name)

    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)


class fixed_attrs_proxy(proxy):
    """
    On attribute lookup, if keyword parameter matching attribute name was
    provided during object construction, returns it's value. Otherwise proxies
    to obj.
    """

    def __init__(self, obj, **kw):
        self._obj = obj
        for k, v in kw.items():
            setattr(self, k, v)


@tg.expose(content_type='text/plain')
def json_validation_error(controller, **kwargs):
    exc = request.validation['exception']
    result = dict(status='Validation Error',
                  errors={fld: str(err) for fld, err in exc.error_dict.items()},
                  value=exc.value,
                  params=kwargs)
    response.status = 400
    return json.dumps(result, indent=2)


def pop_user_notifications(user=None):
    from allura import model as M
    if user is None:
        user = c.user
    mbox = M.Mailbox.query.get(user_id=user._id, is_flash=True)
    if mbox and mbox.queue:
        notifications = M.Notification.query.find(
            dict(_id={'$in': mbox.queue}))
        mbox.queue = []
        mbox.queue_empty = True
        for n in notifications:
            # clean it up so it doesn't hang around
            M.Notification.query.remove({'_id': n._id})
            yield n


def config_with_prefix(d, prefix):
    '''Return a subdictionary keys with a given prefix,
    with the prefix stripped
    '''
    plen = len(prefix)
    return {k[plen:]: v for k, v in d.items()
            if k.startswith(prefix)}


def paging_sanitizer(limit, page, total_count=sys.maxsize, zero_based_pages=True):
    """Return limit, page - both converted to int and constrained to
    valid ranges based on total_count.

    Useful for sanitizing limit and page query params.

    See also g.handle_paging which also checks prefs
    """
    try:
        limit = max(int(limit), 1)
    except ValueError:
        limit = 25
    limit = min(limit, asint(tg.config.get('limit_param_max', 500)))
    max_page = (total_count // limit) + (1 if total_count % limit else 0)
    max_page = max(0, max_page - (1 if zero_based_pages else 0))
    try:
        page = int(page or 0)
    except ValueError:
        page = 0
    page = min(max(page, (0 if zero_based_pages else 1)), max_page)
    return limit, page


def _add_inline_line_numbers_to_text(txt):
    markup_text = '<div class="codehilite"><pre>'
    for line_num, line in enumerate(txt.splitlines(), 1):
        markup_text = markup_text + \
            '<span id="l{}" class="code_block"><span class="lineno">{}</span> {}</span>'.format(
                line_num, line_num, line)
    markup_text = markup_text + '</pre></div>'
    return markup_text


def _add_table_line_numbers_to_text(txt):
    def _prepend_whitespaces(num, max_num):
        num, max_num = str(num), str(max_num)
        diff = len(max_num) - len(num)
        return ' ' * diff + num

    def _len_to_str_column(l, start=1):
        max_num = l + start
        return '\n'.join(map(_prepend_whitespaces, list(range(start, max_num)), [max_num] * l))

    lines = txt.splitlines(True)
    linenumbers = '<td class="linenos"><div class="linenodiv"><pre>' + \
        _len_to_str_column(len(lines)) + '</pre></div></td>'
    markup_text = '<table class="codehilitetable"><tbody><tr>' + \
        linenumbers + '<td class="code"><div class="codehilite"><pre>'
    for line_num, line in enumerate(lines, 1):
        markup_text = markup_text + \
            f'<span id="l{line_num}" class="code_block">{line}</span>'
    markup_text = markup_text + '</pre></div></td></tr></tbody></table>'
    return markup_text


INLINE = 'inline'
TABLE = 'table'


def render_any_markup(name, txt, code_mode=False, linenumbers_style=TABLE):
    """
    renders markdown using allura enhancements if file is in markdown format
    renders any other markup format using the pypeline
    Returns jinja-safe text
    """
    if not txt:
        txt = '<p><em>Empty File</em></p>'
    else:
        fmt = g.pypeline_markup.can_render(name)
        txt = really_unicode(txt)
        if fmt == 'markdown':
            txt = g.markdown.convert(txt)
        else:
            txt = g.pypeline_markup.render(name, txt)
        if not fmt:
            if code_mode and linenumbers_style == INLINE:
                txt = _add_inline_line_numbers_to_text(txt)
            elif code_mode and linenumbers_style == TABLE:
                txt = _add_table_line_numbers_to_text(txt)
            else:
                txt = '<pre>%s</pre>' % txt
    return Markup(txt)


@pass_context
def subrender_jinja_filter(context, value):
    _template = context.eval_ctx.environment.from_string(value)
    result = _template.render(**context)
    return result


def nl2br_jinja_filter(value):
    result = '<br>\n'.join(escape(line) for line in value.split('\n'))
    return Markup(result)


def log_if_changed(artifact, attr, new_val, message):
    """Set `artifact.attr` to `new_val` if changed. Add AuditLog record."""
    from allura import model as M
    if not hasattr(artifact, attr):
        return
    if getattr(artifact, attr) != new_val:
        M.AuditLog.log(message)
        setattr(artifact, attr, new_val)


def get_tool_packages(tool_name):
    "Return package for given tool (e.g. 'forgetracker' for 'tickets')"
    from allura.app import Application
    app = g.entry_points['tool'].get(tool_name.lower())
    if not app:
        return []
    classes = [c for c in app.mro() if c not in Application.mro()]
    return [cls.__module__.split('.')[0] for cls in classes]


def get_first(d, key):
    """Return value for d[key][0] if d[key] is a list with elements, else return d[key].

    Useful to retrieve values from solr index (e.g. `title` and `text` fields),
    which are stored as lists.
    """
    v = d.get(key)
    if isinstance(v, list):
        return v[0] if len(v) > 0 else None
    return v


def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    return value.strftime(format)


@contextmanager
def log_output(log):
    # TODO: replace with contextlib.redirect_stdout and redirect_stderr?
    class Writer:

        def __init__(self, func):
            self.func = func
            self.closed = False

        def write(self, buf):
            self.func(buf)

        def flush(self):
            pass

    _stdout = sys.stdout
    _stderr = sys.stderr
    sys.stdout = Writer(log.info)
    sys.stderr = Writer(log.error)
    try:
        yield log
    finally:
        sys.stdout = _stdout
        sys.stderr = _stderr


def topological_sort(items, partial_order):
    """Perform topological sort.
       items is a list of items to be sorted.
       partial_order is a list of pairs. If pair (a,b) is in it, it means
       that item a should appear before item b.
       Returns a list of the items in one of the possible orders, or None
       if partial_order contains a loop.

       Modified from: http://www.bitformation.com/art/python_toposort.html
    """
    # Original topological sort code written by Ofer Faigon
    # (www.bitformation.com) and used with permission

    def add_arc(graph, fromnode, tonode):
        """Add an arc to a graph. Can create multiple arcs.
           The end nodes must already exist."""
        graph[fromnode].append(tonode)
        # Update the count of incoming arcs in tonode.
        graph[tonode][0] = graph[tonode][0] + 1

    # step 1 - create a directed graph with an arc a->b for each input
    # pair (a,b).
    # The graph is represented by a dictionary. The dictionary contains
    # a pair item:list for each node in the graph. /item/ is the value
    # of the node. /list/'s 1st item is the count of incoming arcs, and
    # the rest are the destinations of the outgoing arcs. For example:
    #           {'a':[0,'b','c'], 'b':[1], 'c':[1]}
    # represents the graph:   c <-- a --> b
    # The graph may contain loops and multiple arcs.
    # Note that our representation does not contain reference loops to
    # cause GC problems even when the represented graph contains loops,
    # because we keep the node names rather than references to the nodes.
    graph = defaultdict(lambda: [0])
    for a, b in partial_order:
        add_arc(graph, a, b)

    # Step 2 - find all roots (nodes with zero incoming arcs).
    roots = [n for n in items if graph[n][0] == 0]
    roots.reverse()  # keep sort stable

    # step 3 - repeatedly emit a root and remove it from the graph. Removing
    # a node may convert some of the node's direct children into roots.
    # Whenever that happens, we append the new roots to the list of
    # current roots.
    sorted = []
    while roots:
        # If len(roots) is always 1 when we get here, it means that
        # the input describes a complete ordering and there is only
        # one possible output.
        # When len(roots) > 1, we can choose any root to send to the
        # output; this freedom represents the multiple complete orderings
        # that satisfy the input restrictions. We arbitrarily take one of
        # the roots using pop(). Note that for the algorithm to be efficient,
        # this operation must be done in O(1) time.
        root = roots.pop()
        sorted.append(root)
        for child in graph[root][1:]:
            graph[child][0] = graph[child][0] - 1
            if graph[child][0] == 0:
                roots.append(child)
        del graph[root]
    if len(graph) > 0:
        # There is a loop in the input.
        return None
    return sorted


@contextmanager
def ming_config(**conf):
    r"""Temporarily swap in a new ming configuration, restoring the previous
    one when the contextmanager exits.

    :param \*\*conf: keyword arguments defining the new ming configuration

    """
    import ming
    from ming.session import Session
    datastores = Session._datastores
    try:
        utils.configure_ming(conf)
        yield
    finally:
        Session._datastores = datastores
        for name, session in Session._registry.items():
            session.bind = datastores.get(name, None)
            session._name = name


@contextmanager
def ming_config_from_ini(ini_path):
    """Temporarily swap in a new ming configuration, restoring the previous
    one when the contextmanager exits.

    :param ini_path: Path to ini file containing the ming configuration

    """
    root = pkg_resources.get_distribution('allura').location
    conf = appconfig('config:%s' % os.path.join(root, ini_path))
    with ming_config(**conf):
        yield


def shlex_split(string):
    # py2/3 compatibility
    return [six.ensure_text(s) for s in shlex.split(six.ensure_str(string))]


def split_select_field_options(field_options):
    try:
        field_options = shlex_split(field_options)
    except ValueError:
        field_options = field_options.split()
        # After regular split field_options might contain a " characters,
        # which would break html when rendered inside tag's value attr.
        # Escaping doesn't help here, 'cause it breaks EasyWidgets' validation,
        # so we're getting rid of those.
        field_options = [o.replace('"', '') for o in field_options]
    return field_options


@contextmanager
def notifications_disabled(project, disabled=True):
    """Temporarily disable email notifications on a project.

    """
    orig = project.notifications_disabled
    try:
        project.notifications_disabled = disabled
        yield
    finally:
        project.notifications_disabled = orig


@contextmanager
def null_contextmanager(returning=None, *args, **kw):
    """A no-op contextmanager.

    """
    yield returning


class exceptionless:

    '''Decorator making the decorated function return 'error_result' on any
    exceptions rather than propagating exceptions up the stack
    '''

    def __init__(self, error_result, log=None):
        self.error_result = error_result
        self.log = log

    def __call__(self, fun):
        fname = 'exceptionless(%s)' % fun.__name__

        def inner(*args, **kwargs):
            try:
                return fun(*args, **kwargs)
            except Exception as e:
                if self.log:
                    self.log.exception(
                        'Error calling %s(args=%s, kwargs=%s): %s',
                        fname, args, kwargs, str(e))
                return self.error_result
        inner.__name__ = str(fname)
        return inner


def urlopen(url, retries=3, codes=(408, 500, 502, 503, 504), timeout=None):
    """Open url, optionally retrying if an error is encountered.

    Socket and other IO errors will always be retried if retries > 0.
    HTTP errors are retried if the error code is passed in ``codes``.

    :param retries: Number of time to retry.
    :param codes: HTTP error codes that should be retried.

    """
    attempts = 0
    while True:
        try:
            return six.moves.urllib.request.urlopen(url, timeout=timeout)
        except OSError as e:
            no_retry = isinstance(e, six.moves.urllib.error.HTTPError) and e.code not in codes
            if attempts < retries and not no_retry:
                attempts += 1
                continue
            else:
                try:
                    url_string = url.get_full_url()  # if url is Request obj
                except Exception:
                    url_string = url
                if hasattr(e, 'filename') and url_string != e.filename:
                    url_string += f' => {e.filename}'
                if timeout is None:
                    timeout = socket.getdefaulttimeout()
                if getattr(e, 'fp', None):
                    body = e.fp.read()
                else:
                    body = ''
                log.exception(
                    'Failed after %s retries on url with a timeout of %s: %s: %s',
                    attempts, timeout, url_string, body[:250])
                raise e


def plain2markdown(txt, preserve_multiple_spaces=False, has_html_entities=False):
    if not has_html_entities:
        # prevent &foo; and &#123; from becoming HTML entities
        txt = re_amp.sub('&amp;', txt)
    # avoid accidental 4-space indentations creating code blocks
    if preserve_multiple_spaces:
        txt = txt.replace('\t', ' ' * 4)
        txt = re_preserve_spaces.sub('&nbsp;', txt)
    else:
        txt = re_leading_spaces.sub('', txt)
    try:
        # try to use html2text for most of the escaping
        import html2text
        html2text.BODY_WIDTH = 0
        txt = html2text.escape_md_section(txt, snob=True)
    except ImportError:
        # fall back to just escaping any MD-special chars
        txt = md_chars_matcher_all.sub(r"\\\1", txt)
    # prevent < and > from becoming tags
    txt = re_angle_bracket_open.sub('&lt;', txt)
    txt = re_angle_bracket_close.sub('&gt;', txt)
    return txt


OrderedDefaultDict = defaultdict  # py3.7 dicts are always ordered


def iter_entry_points(group, *a, **kw):
    """Yields entry points that have not been disabled in the config.

    If ``group`` is "allura" (Allura tool entry points) or one of subgroups
    (e.g. "allura.phone"), this function also checks for multiple entry points
    with the same name. If there are multiple entry points with the same name,
    and one of them is a subclass of the other(s), it will be yielded, and the
    other entry points with that name will be ignored. If a subclass is not
    found, an ImportError will be raised.

    This treatment of "allura" and "allura.*" entry points allows tool authors
    to subclass another tool while reusing the original entry point name.

    """
    def active_eps():
        disabled = aslist(
            tg.config.get('disable_entry_points.' + group), sep=',')
        return [ep for ep in pkg_resources.iter_entry_points(group, *a, **kw)
                if ep.name not in disabled]

    def unique_eps(entry_points):
        by_name = OrderedDefaultDict(list)
        for ep in entry_points:
            by_name[ep.name].append(ep)
        for name, eps in by_name.items():
            ep_count = len(eps)
            if ep_count == 1:
                yield eps[0]
            else:
                yield subclass(eps)

    def subclass(entry_points):
        loaded = {ep: ep.load() for ep in entry_points}
        for ep, cls in loaded.items():
            others = list(loaded.values())[:]
            others.remove(cls)
            if all([issubclass(cls, other) for other in others]):
                return ep
        raise ImportError('Ambiguous [allura] entry points detected. ' +
                          'Multiple entry points with name "%s".' % entry_points[0].name)
    is_allura = group == 'allura' or group.startswith('allura.')
    return iter(unique_eps(active_eps()) if is_allura else active_eps())


# http://stackoverflow.com/a/1060330/79697
def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


@contextmanager
def login_overlay(exceptions=None):
    """
    Override the default behavior of redirecting to the auth.login_url and
    instead display an overlay with content from auth.login_fragment_url.

    This is to allow pages that require authentication for any actions but
    not for the initial view to be more apparent what you will get once
    logged in.

    This should be wrapped around call to `require_access()` (presumably in
    the `_check_security()` method on a controller).  The `exceptions` param
    can be given a list of exposed views to leave with the original behavior.

    For example::

        class MyController(BaseController);
            def _check_security(self):
                with login_overlay(exceptions=['process']):
                    require_access(self.neighborhood, 'register')

            @expose
            def index(self, *args, **kw):
                return {}

            @expose
            def list(self, *args, **kw):
                return {}

            @expose
            def process(self, *args, **kw):
                return {}

    This would show the overlay to unauthenticated users who visit `/`
    or `/list` but would perform the normal redirect when `/process` is
    visited.
    """
    try:
        yield
    except HTTPUnauthorized:
        if exceptions:
            for exception in exceptions:
                if request.path.rstrip('/').endswith('/%s' % exception):
                    raise
        c.show_login_overlay = True


def unidiff(old, new):
    """Returns unified diff between `one` and `two`."""
    return '\n'.join(difflib.unified_diff(
        a=old.splitlines(),
        b=new.splitlines(),
        fromfile='old',
        tofile='new',
        lineterm=''))


def auditlog_user(message, *args, **kwargs):
    """
    Create an audit log entry for a user, including the IP address

    :param str message:
    :param user: a :class:`allura.model.auth.User`
    """
    from allura import model as M
    ip_address = utils.ip_address(request)
    message = f'IP Address: {ip_address}\nUser-Agent: {request.user_agent}\n' + message
    if c.user and kwargs.get('user') and kwargs['user'] != c.user:
        message = f'Done by user: {c.user.username}\n' + message
    return M.AuditLog.log_user(message, *args, **kwargs)


def get_user_status(user):
    '''
    Get user status based on disabled and pending attrs

    :param user: a :class:`allura.model.auth.User`
    '''
    disabled = user.disabled
    pending = user.pending

    if not disabled and not pending:
        return 'enabled'
    elif disabled:
        return 'disabled'
    elif pending:
        return 'pending'


def rate_limit(cfg_opt, artifact_count, start_date, exception=None):
    """
    Check the various config-defined artifact creation rate limits, and if any
    are exceeded, raise exception.

    :param artifact_count: a number or callable (for lazy evaluation)
    """
    if exception is None:
        exception = exc.RatelimitError
    rate_limits = json.loads(tg.config.get(cfg_opt, '{}'))
    now = datetime.utcnow()
    for rate, count in rate_limits.items():
        age = now - start_date
        age = (age.microseconds + (age.seconds + age.days * 24 * 3600) * 10 ** 6) / 10 ** 6
        if age < int(rate):
            if callable(artifact_count):
                artifact_count = artifact_count()
            if artifact_count >= count:
                raise exception()


def base64uri(content_or_image, image_format='PNG', mimetype='image/png', windows_line_endings=False):
    if hasattr(content_or_image, 'save'):
        output = BytesIO()
        content_or_image.save(output, format=image_format)
        content = output.getvalue()
    else:
        content = content_or_image

    if windows_line_endings:
        content = content.replace('\n', '\r\n')

    data = six.ensure_text(base64.b64encode(six.ensure_binary(content)))
    return f'data:{mimetype};base64,{data}'


def slugify(name, allow_periods=False):
    """
    Returns a tuple with slug and lowered slug based on name
    """
    RE_NON_ALPHA_ETC = re.compile(r'[^.\w]+' if allow_periods else r'[^\w]+')
    slug = RE_NON_ALPHA_ETC.sub('-',  # replace non ". alphanum_" sequences into single -
                                unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().replace("'", '')  # asciify & strip apostophes.   https://stackoverflow.com/a/53261200
                                ).strip('-')  # leading - or trailing - gets removed
    return slug, slug.lower()


email_re = re.compile(r'(([a-z0-9_]|\-|\.)+)@([\w\.-]+)', re.IGNORECASE)


def hide_private_info(message):
    if asbool(tg.config.get('hide_private_info', 'true')) and message:
        hidden = email_re.sub(r'\1@...', message)
        if type(message) not in (str,):
            # custom subclass like markupsafe.Markup, convert to that type again
            hidden = type(message)(hidden)
        return hidden
    else:
        return message


def emojize(text):
    """Coverts emoji codes to unicode emojis"""
    return emoji.emojize(text, language="alias")


def get_current_reaction(react_users_dict):
    """Return current selected reaction for given react_users dict"""
    return utils.get_key_from_value(react_users_dict, c.user.username)


def username_project_url(user_or_username):
    from allura.lib import plugin

    url = None

    if not user_or_username:
        return url

    if isinstance(user_or_username, str):
        class UserName:
            def __init__(self, username):
                self.username = username
        username = user_or_username
        auth_provider = plugin.AuthenticationProvider.get(request)
        try:
            # in 99% of cases, we can get away without a DB lookup
            url = auth_provider.user_project_url(UserName(username))
        except AttributeError:
            user = auth_provider.by_username(username)
            url = user.url()
    else:
        user = user_or_username
        url = user.url()

    return f'{url}profile/'


def pluralize_tool_name(tool_name: string, count: int):
    pluralize_tools = ['Wiki', 'Discussion', 'Blog']
    if tool_name is not None and tool_name in pluralize_tools:
        return f"{tool_name}{'s'[:count^1]}"
    return tool_name
