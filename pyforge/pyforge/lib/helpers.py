# -*- coding: utf-8 -*-

"""WebHelpers used in pyforge."""

from webhelpers import date, feedgenerator, html, number, misc, text
from contextlib import contextmanager

from pyforge import model as M

def make_users(uids):
    return (M.User.m.get(_id=uid) for uid in uids)

def make_roles(ids):
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
