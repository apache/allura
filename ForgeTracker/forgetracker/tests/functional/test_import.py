import os
import json
from datetime import datetime, timedelta
from nose.tools import assert_equal

import ming
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g

from allura import model as M
from alluratest.controller import TestController, TestRestApiBase


class TestImportController(TestRestApiBase):#TestController):

    def new_ticket(self, mount_point='/bugs/', **kw):
        response = self.app.get(mount_point + 'new/')
        form = response.forms[1]
        for k, v in kw.iteritems():
            form['ticket_form.%s' % k] = v
        resp = form.submit()
        if resp.status_int == 200:
            resp.showbrowser()
            assert 0, "form error?"
        return resp.follow()

    def set_api_ticket(self, caps={'import': 'test'}):
        api_ticket = M.ApiTicket(user_id=self.user._id, capabilities=caps,
                                 expires=datetime.utcnow() + timedelta(days=1))
        ming.orm.session(api_ticket).flush()
        self.set_api_token(api_ticket)


    def test_no_capability(self):
        here_dir = os.path.dirname(__file__)

        self.set_api_ticket({'import2': 'test'})
        resp = self.api_post('/rest/p/test/bugs/perform_import',
            doc=open(here_dir + '/data/sf.json').read(), options='{}')
        assert resp.status_int == 403

        self.set_api_ticket({'import': 'test2'})
        resp = self.api_post('/rest/p/test/bugs/perform_import',
            doc=open(here_dir + '/data/sf.json').read(), options='{}')
        assert resp.status_int == 403

        self.set_api_ticket({'import': 'test'})
        resp = self.api_post('/rest/p/test/bugs/perform_import',
            doc=open(here_dir + '/data/sf.json').read(), options='{}')
        assert resp.status_int == 200

    @staticmethod
    def time_normalize(t):
        return t.replace('T', ' ').replace('Z', '')

    def verify_ticket(self, from_api, org):
        assert_equal(from_api['status'], org['status'])
        assert_equal(from_api['description'], org['description'])
        assert_equal(from_api['summary'], org['summary'])
        assert_equal(from_api['ticket_num'], org['id'])
        assert_equal(from_api['created_date'], self.time_normalize(org['date']))
        assert_equal(from_api['mod_date'], self.time_normalize(org['date_updated']))
        assert_equal(from_api['custom_fields']['_resolution'], org['resolution'])
        assert_equal(from_api['custom_fields']['_cc'], org['cc'])
        assert_equal(from_api['custom_fields']['_private'], org['private'])

    def test_validate_import(self):
        here_dir = os.path.dirname(__file__)
        doc_text = open(here_dir + '/data/sf.json').read()
        r = self.api_post('/rest/p/test/bugs/validate_import',
            doc=doc_text, options='{}')
        assert not r.json['errors']

    def test_import(self):
        here_dir = os.path.dirname(__file__)
        api_ticket = M.ApiTicket(user_id=self.user._id, capabilities={'import': 'test'}, 
                                 expires=datetime.utcnow() + timedelta(days=1))
        ming.orm.session(api_ticket).flush()
        self.set_api_token(api_ticket)

        doc_text = open(here_dir + '/data/sf.json').read()
        doc_json = json.loads(doc_text)
        ticket_json = doc_json['trackers']['default']['artifacts'][0]
        r = self.api_post('/rest/p/test/bugs/perform_import',
            doc=doc_text, options='{"user_map": {"hinojosa4": "test-admin", "ma_boehm": "test-user"}}')
        assert r.json['status']
        assert r.json['errors'] == []

        ming.orm.ThreadLocalORMSession.flush_all()
        M.MonQTask.run_ready()
        ming.orm.ThreadLocalORMSession.flush_all()

        indexed_tickets = filter(lambda a: a['type_s'] == 'Ticket', g.solr.db.values())
        assert len(indexed_tickets) == 1
        assert indexed_tickets[0]['summary_t'] == ticket_json['summary']
        assert indexed_tickets[0]['ticket_num_i'] == ticket_json['id']

        r = self.app.get('/rest/p/test/bugs/204/')
        self.verify_ticket(r.json['ticket'], ticket_json)
        assert r.json['ticket']["reported_by"] == "test-user"
        assert r.json['ticket']["assigned_to"] == "test-admin"

        r = self.app.get('/rest/p/test/bugs/')
        assert len(r.json['tickets']) == 1
        assert_equal(r.json['tickets'][0]['ticket_num'], ticket_json['id'])
        assert_equal(r.json['tickets'][0]['summary'], ticket_json['summary'])

        r = self.app.get('/p/test/bugs/204/')
        assert ticket_json['summary'] in r
        r = self.app.get('/p/test/bugs/')
        assert ticket_json['summary'] in r
