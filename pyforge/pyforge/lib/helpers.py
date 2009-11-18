# -*- coding: utf-8 -*-

"""WebHelpers used in pyforge."""

from webhelpers import date, feedgenerator, html, number, misc, text

from pyforge import model as M

def make_users(uids):
    return (M.User.m.get(_id=uid) for uid in uids)
