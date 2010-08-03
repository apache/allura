# -*- coding: utf-8 -*-
import os
import os.path
import difflib
import urllib
import re
import Image
import json
import logging
from hashlib import sha1
from datetime import datetime

import tg
import genshi.template
from formencode.validators import FancyValidator
from dateutil.parser import parse
from pymongo.bson import ObjectId
from pymongo.errors import InvalidId
from contextlib import contextmanager
from pylons import c, response, request
from tg.decorators import before_validate
from formencode.variabledecode import variable_decode

from webhelpers import date, feedgenerator, html, number, misc, text

from pymongo import bson

re_path_portion = re.compile(r'^[a-z][-a-z0-9]{2,}$')

def find_project(url_path):
    from pyforge import model as M
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
        p = M.Project.query.get(shortname=shortname, deleted=False)
        if p: return p, parts[length:]
        length -= 1
    return None, url_path.split('/')

def find_executable(exe_name):
    '''Find the abspath of a given executable (which
    must be on the PATH)'''
    for dirname in os.environ['PATH'].split(os.pathsep):
        path = os.path.join(dirname, exe_name)
        if os.access(path, os.X_OK): return path
    
def make_neighborhoods(uids):
    from pyforge import model as M
    result = (M.Neighborhood.query.get(_id=uid) for uid in uids)
    return (r for r in result if r is not None)

def make_projects(uids):
    from pyforge import model as M
    result = (M.Project.query.get(_id=uid) for uid in uids)
    return (r for r in result if r is not None)

def make_users(uids):
    from pyforge import model as M
    result = (M.User.query.get(_id=uid) for uid in uids)
    return (r for r in result if r is not None)

def make_roles(ids):
    from pyforge import model as M
    result = (M.ProjectRole.query.get(_id=id) for id in ids)
    return (pr for pr in result if pr is not None)

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
        for k,v in saved_attrs.iteritems():
            setattr(obj, k, v)
        for k in new_attrs:
            delattr(obj, k)

def sharded_path(name, num_parts=2):
    parts = [
        name[:i+1]
        for i in range(num_parts) ]
    return '/'.join(parts)

def mixin_reactors(cls, module, prefix=None):
    'attach the reactor-decorated functions in module to the given class'
    from .decorators import ConsumerDecoration
    if prefix is None: prefix = module.__name__ + '.'
    for name in dir(module):
        value = getattr(module, name)
        if ConsumerDecoration.get_decoration(value, False):
            setattr(cls, prefix + name, staticmethod(value))


class NoSuchProjectError(Exception):
    pass


def set_context(project_shortname, mount_point=None, app_config_id=None):
    from pyforge import model
    p = model.Project.query.get(shortname=project_shortname)
    if p is None:
        try:
            p = model.Project.query.get(_id=ObjectId(str(project_shortname)))
        except InvalidId:
            pass

    if p is None:
        raise NoSuchProjectError("Couldn't find project %s" %
                                 repr(project_shortname))
    c.project = p

    if app_config_id is None:
        c.app = p.app_instance(mount_point)
    else:
        if isinstance(app_config_id, basestring):
            app_config_id = bson.ObjectId(app_config_id)
        app_config = model.AppConfig.query.get(_id=app_config_id)
        c.app = p.app_instance(app_config)

@contextmanager
def push_context(project_id, mount_point=None, app_config_id=None):
    project = getattr(c, 'project', ())
    app = getattr(c, 'app', ())
    set_context(project_id, mount_point, app_config_id)
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
        for k,v in d.iteritems())

def vardec(fun):
    def hook(remainder, params):
        new_params = variable_decode(params)
        params.update(new_params)
    before_validate(hook)(fun)
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

    granularities = ['century', 'decade', 'year', 'month', 'day', 'hour',
                     'minute']
    end_time = datetime.utcnow()

    while True:
        granularity = granularities.pop()
        ago = date.distance_of_time_in_words(
            start_time, end_time, granularity, round=True)
        rounded_to_one_granularity = 'and' not in ago
        if rounded_to_one_granularity:
            break
    return ago + ' ago'

def ago_ts(timestamp):
    return ago(datetime.fromtimestamp(timestamp))

def tag_artifact(artifact, user, tags):
    from pyforge import model as M
    aref = artifact.dump_ref()
    when = datetime.utcnow()
    # Get the UserTags object
    ut = M.UserTags.upsert(user, aref)
    # Determine which tags were added/removed
    user_tags = set(tag.tag for tag in ut.tags)
    tags = set(tags)
    added_tags = list(tags - user_tags)
    removed_tags = list(user_tags - tags)
    # Create the TagEvent
    evt = M.TagEvent(
        when=when,
        user_id=user._id,
        artifact_ref=aref,
        added_tags=added_tags,
        removed_tags=removed_tags)
    # Update the UserTags Object
    ut.add_tags(when, added_tags)
    ut.remove_tags(removed_tags)
    # Update the artifact
    artifact.add_tags(added_tags)
    artifact.remove_tags(removed_tags)
    # Update the Tag index
    M.Tag.add(aref, user, added_tags)
    M.Tag.remove(aref, user, removed_tags)

def square_image(image):
    # image is wider than tall, so center horizontally
    height = image.size[0]
    width = image.size[1]
    if height < width:
        new_image = Image.new("RGB", (width, width), 'white')
        new_image.paste(image, ((width-height)/2, 0))
        image = new_image
    # image is taller than wide, so center vertically
    elif height > width:
        new_image = Image.new("RGB", (height, height), 'white')
        new_image.paste(image, (0, (height-width)/2))
        image = new_image
    return image

def supported_by_PIL(file_type):
    return str(file_type).lower() in ['image/jpg','image/png','image/jpeg','image/gif']

def save_image(icon, file_class, square=False, thumbnail_size=None, meta=None,
               save_original=False, original_meta=None):
    if icon is not None and icon != '':
        if supported_by_PIL(icon.type):
            if not meta:
                meta = dict()
            filename = icon.filename
            if icon.type: content_type = icon.type
            else: content_type = 'application/octet-stream'
            image = Image.open(icon.file)
            format = image.format
            if save_original:
                if not original_meta:
                    original_meta = dict()
                with file_class.create(
                    content_type=content_type,
                    filename=filename,
                    **original_meta) as fp:
                    filename = fp.name
                    image.save(fp, format)
            if square_image:
                image = square_image(image)
            if thumbnail_size:
                image.thumbnail(thumbnail_size, Image.ANTIALIAS)
            with file_class.create(
                content_type=content_type,
                filename=filename,
                **meta) as fp:
                image.save(fp, format)
        else:
            tg.flash('The icon must be jpg, png, or gif format.')

class DateTimeConverter(FancyValidator):

    def _to_python(self, value, state):
        return parse(value)

    def _from_python(self, value, state):
        return value.isoformat()

def absurl(url):
    from tg import request
    if '://' in url: return url
    return request.scheme + '://' + request.host + url

def diff_text(t1, t2, differ=None):
    t1_words = re.split(' ', t1)
    t2_words = re.split(' ', t2)
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

def diff_text_genshi(t1, t2):
    Markup = genshi.Markup
    differ = difflib.SequenceMatcher(None, t1, t2)
    result = []
    def esc(t):
        try:
            return genshi.escape(t.replace('\n', '\n    '))
        except UnicodeDecodeError:
            return '**UnicodeDecodeError**'
    def excerpt(text, a, b):
        if b-a > 1000:
            return text[a:a+400] + '...' + text[b-400:b]
        else:
            return text[a:b]
    yield '    '
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag in ('delete', 'replace'):
            yield '<del>'
            yield esc(excerpt(t1,i1,i2))
            yield '</del>'
        if tag in ('insert', 'replace'):
            yield '<ins>'
            yield esc(excerpt(t2,j1,j2))
            yield '</ins>'
        if tag == 'equal':
            yield esc(excerpt(t1,i1,i2))

def gen_message_id():
    parts = c.project.url().split('/')[1:-1]
    return '%s.%s@%s.sourceforge.net' % (nonce(40),
                                         c.app.config.options['mount_point'],
                                         '.'.join(reversed(parts)))

class ProxiedAttrMeta(type):
    def __init__(cls, name, bases, dct):
        for v in dct.itervalues():
            if isinstance(v, attrproxy):
                v.cls = cls

class attrproxy(object):
    cls=None
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
    response.status=400
    return json.dumps(result, indent=2)

def pop_user_notifications(user=None):
    from pyforge import model as M
    if user is None: user = c.user
    mbox = M.Mailbox.query.get(user_id=user._id, type='flash')
    if mbox:
        notifications = M.Notification.query.find(dict(_id={'$in':mbox.queue}))
        mbox.queue = []
        for n in notifications: yield n
    
def config_with_prefix(d, prefix):
    '''Return a subdictionary keys with a given prefix,
    with the prefix stripped
    '''
    plen=len(prefix)
    return dict((k[plen:], v) for k,v in d.iteritems()
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

class exceptionless(object):
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
            except:
                if self.log:
                    self.log.exception('Error calling %s', fname)
                return self.error_result
        inner.__name__ = fname
        return inner

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
        for k,v in meta.iteritems():
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
    warn=warning

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
                ip_address = ip_address.split(',')[0].strip()
                result['ip_address'] = ip_address
            except TypeError:
                pass
            return result
        except:
            self._logger.warning('Error logging to rtstats, some info may be missing', exc_info=True)
            return result
