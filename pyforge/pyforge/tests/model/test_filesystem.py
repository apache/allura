# -*- coding: utf-8 -*-
"""
Model tests for auth
"""
import mock
from pylons import c, g
from ming.orm.ormsession import ThreadLocalORMSession

from pyforge import model as M
from pyforge.lib.app_globals import Globals

def setUp():
    g._push_object(Globals())
    c._push_object(mock.Mock())
    ThreadLocalORMSession.close_all()
    g.set_project('projects/test')
    g.set_app('hello')
    M.File.remove({})
    c.user = M.User.query.get(username='test_admin')

def test_file():
    f = M.File.save('test.txt', 'text/plain', '')
    f = M.File.save('test.txt', 'text/plain', 'This is some text')
    assert f.filename != 'test.txt'
    f1 = M.File.by_metadata(filename='test.txt').one()
    assert f1 is f
    with M.File.create('text/plain', filename='test1.txt') as fp:
        print >> fp, 'This is another file'
    assert len(M.File.list()) == 2
    with f1.open() as fp:
        assert fp.read() == 'This is some text'
    f1.delete()
    assert len(M.File.list()) == 1
