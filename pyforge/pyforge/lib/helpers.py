# -*- coding: utf-8 -*-
import os
from hashlib import sha1
from datetime import datetime

from pymongo.bson import ObjectId
from contextlib import contextmanager
from pylons import c
from tg.decorators import before_validate
from formencode.variabledecode import variable_decode

from webhelpers import date, feedgenerator, html, number, misc, text

from pymongo import bson

def find_project(url_path):
    from pyforge import model as M
    length = len(url_path)
    while length:
        id = '/'.join(url_path[:length]) + '/'
        p = M.Project.query.get(_id=id)
        if p: return p, url_path[length:]
        length -= 1
    return None, url_path

def find_executable(exe_name):
    '''Find the abspath of a given executable (which
    must be on the PATH)'''
    for dirname in os.environ['PATH'].split(os.pathsep):
        path = os.path.join(dirname, exe_name)
        if os.access(path, os.X_OK): return path
    
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

def set_context(project_id, mount_point=None, app_config_id=None):
    from pyforge import model
    p = model.Project.query.get(_id=project_id)
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

def ago(dt):
    return date.distance_of_time_in_words(dt, datetime.utcnow(),
                                          'minute',
                                          round=True) + ' ago'
