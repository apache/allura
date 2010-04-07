# -*- coding: utf-8 -*-
import os
import difflib
import urllib
import re
from hashlib import sha1
from datetime import datetime

from formencode.validators import FancyValidator
from dateutil.parser import parse
from pymongo.bson import ObjectId
from contextlib import contextmanager
from pylons import c
from tg.decorators import before_validate
from formencode.variabledecode import variable_decode

from webhelpers import date, feedgenerator, html, number, misc, text

from pymongo import bson

re_path_portion = re.compile(r'^[a-z][_a-z0-9]{2,}$')

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
        p = M.Project.query.get(shortname=shortname)
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
    return (M.Neighborhood.query.get(_id=uid) for uid in uids)

def make_projects(uids):
    from pyforge import model as M
    return (M.Project.query.get(_id=uid) for uid in uids)

def make_users(uids):
    from pyforge import model as M
    return (M.User.query.get(_id=uid) for uid in uids)

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
    yield obj
    for k,v in saved_attrs.iteritems():
        setattr(obj, k, v)
    for k in new_attrs:
        delattr(obj, k)

def mixin_reactors(cls, module, prefix=None):
    'attach the reactor-decorated functions in module to the given class'
    from .decorators import ConsumerDecoration
    if prefix is None: prefix = module.__name__ + '.'
    for name in dir(module):
        value = getattr(module, name)
        if ConsumerDecoration.get_decoration(value, False):
            setattr(cls, prefix + name, staticmethod(value))

def set_context(project_shortname, mount_point=None, app_config_id=None):
    from pyforge import model
    p = model.Project.query.get(shortname=project_shortname)
    if p is None:
        p = model.Project.query.get(_id=ObjectId(str(project_shortname)))
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
    yield
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

def ago(dt, round=False):
    ago = date.distance_of_time_in_words(dt, datetime.utcnow(),
                                          'minute',
                                          round=True)
    if round:
        ago = ago.split(' and')[0]
    return ago + ' ago'

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
    if image.size[0] < image.size[1]:
        h_offset = (image.size[1]-image.size[0])/2
        image = image.crop((0, h_offset, image.size[0], image.size[0]+h_offset))
    elif image.size[0] > image.size[1]:
        w_offset = (image.size[0]-image.size[1])/2
        image = image.crop((w_offset, 0, image.size[1]+w_offset, image.size[1]))
    return image

class DateTimeConverter(FancyValidator):

    def _to_python(self, value, state):
        return parse(value)

    def _from_python(self, value, state):
        return value.isoformat()

def absurl(url):
    from tg import request
    if '://' in url: return url
    return request.scheme + '://' + request.host + url

def diff_text(t1, t2):
    differ = difflib.SequenceMatcher(None, t1, t2)
    result = []
    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag in ('delete', 'replace'):
            result += [ '<del>', t1[i1:i2], '</del>' ]
        if tag in ('insert', 'replace'):
            result += [ '<ins>', t2[j1:j2], '</ins>' ]
        if tag == 'equal':
            result += t1[i1:i2]
    return ''.join(result).replace('\n', '<br/>\n')

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
