# -*- coding: utf-8 -*-
import time
import unittest

import pylons
from webob import Request

from ming.orm import state
from alluratest.controller import setup_unit_test

from allura.lib import utils

class TestChunkedIterator(unittest.TestCase):

    def setUp(self):
        from allura import model as M
        setup_unit_test()
        for i in range(10):
            p = M.Project(shortname='pp%d' % i)
            M.session.main_orm_session.insert_now(p, state(p))
        M.session.project_orm_session.clear()

    def test_can_iterate(self):
        from allura import model as M
        chunks = [
            chunk for chunk in utils.chunked_find(M.Project, {}, 2) ]
        assert len(chunks) > 1, chunks

class TestAntispam(unittest.TestCase):

    def setUp(self):
        setup_unit_test()
        pylons.request.remote_addr = '127.0.0.1'
        self.a = utils.AntiSpam()

    def test_generate_fields(self):
        fields = '\n'.join(self.a.extra_fields())
        assert 'name="timestamp"' in fields, fields
        assert 'name="spinner"' in fields, fields
        assert ('class="%s"' % self.a.honey_class) in fields, fields

    def test_valid_submit(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        validated = utils.AntiSpam.validate_request(r)
        assert dict(a='1', b='2') == validated, validated

    def test_invalid_old(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        self.assertRaises(
            ValueError,
            utils.AntiSpam.validate_request,
            r, now=time.time()+60*60+1)

    def test_invalid_future(self):
        form = dict(a='1', b='2')
        r = Request.blank('/', POST=self._encrypt_form(**form))
        self.assertRaises(
            ValueError,
            utils.AntiSpam.validate_request,
            r, now=time.time()-10)

    def test_invalid_spinner(self):
        form = dict(a='1', b='2')
        eform = self._encrypt_form(**form)
        eform['spinner'] += 'a'
        r = Request.blank('/', POST=eform)
        self.assertRaises(ValueError, utils.AntiSpam.validate_request, r)

    def test_invalid_honey(self):
        form = dict(a='1', b='2', honey0='a')
        eform = self._encrypt_form(**form)
        r = Request.blank('/', POST=eform)
        self.assertRaises(ValueError, utils.AntiSpam.validate_request, r)

    def _encrypt_form(self, **kwargs):
        encrypted_form = dict(
            (self.a.enc(k), v) for k,v in kwargs.items())
        encrypted_form.setdefault(self.a.enc('honey0'), '')
        encrypted_form.setdefault(self.a.enc('honey1'), '')
        encrypted_form['spinner'] = self.a.spinner_text
        encrypted_form['timestamp'] = self.a.timestamp_text
        return encrypted_form
