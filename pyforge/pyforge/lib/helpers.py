# -*- coding: utf-8 -*-

"""WebHelpers used in pyforge."""
from pylons import c

from webhelpers import date, feedgenerator, html, number, misc, text
from contextlib import contextmanager

def make_users(uids):
    from pyforge import model as M
    return (M.User.m.get(_id=uid) for uid in uids)

def make_roles(ids):
    from pyforge import model as M
    return (M.ProjectRole.m.get(_id=id) for id in ids)

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

def set_context(project_id, mount_point):
    from pyforge import model
    p = model.Project.m.get(_id=project_id)
    c.project = p
    c.app = p.app_instance(mount_point)
