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

from datetime import datetime, timedelta

import mock
from tg import tmpl_context as c
from ming.orm.ormsession import ThreadLocalORMSession

import forgetracker
from forgetracker.model import Globals
from forgetracker.tests.unit import TrackerTestWithModel
from allura.lib import helpers as h


class TestGlobalsModel(TrackerTestWithModel):

    def setup_method(self, method):
        super().setup_method(method)
        c.project.install_app('Tickets', 'doc-bugs')
        ThreadLocalORMSession.flush_all()

    def test_it_has_current_tracker_globals(self):
        bugs_globals = Globals.query.get(app_config_id=c.app.config._id)
        assert c.app.globals == bugs_globals
        h.set_context('test', 'doc-bugs', neighborhood='Projects')
        assert c.app.globals != bugs_globals

    def test_next_ticket_number_increments(self):
        gl = Globals()
        assert gl.next_ticket_num() == 1
        assert gl.next_ticket_num() == 2

    def test_ticket_numbers_are_independent(self):
        with h.push_context('test', 'doc-bugs', neighborhood='Projects'):
            assert c.app.globals.next_ticket_num() == 1
        with h.push_context('test', 'bugs', neighborhood='Projects'):
            assert c.app.globals.next_ticket_num() == 1

    @mock.patch('forgetracker.model.ticket.datetime')
    def test_bin_count(self, mock_dt):
        now = datetime.utcnow()
        mock_dt.utcnow.return_value = now
        gbl = Globals()
        gbl._bin_counts_data = [{'summary': 'foo', 'hits': 1},
                                {'summary': 'bar', 'hits': 2}]
        gbl.invalidate_bin_counts = mock.Mock()

        # not expired, finds bin
        gbl.invalidate_bin_counts.reset_mock()
        gbl._bin_counts_expire = now + timedelta(minutes=5)
        bin = gbl.bin_count('bar')
        assert bin['hits'] == 2
        assert not gbl.invalidate_bin_counts.called

        # expired, returns value for missing bin
        gbl.invalidate_bin_counts.reset_mock()
        gbl._bin_counts_expire = now - timedelta(minutes=5)
        bin = gbl.bin_count('qux')
        assert bin['hits'] == 0
        assert gbl.invalidate_bin_counts.called

        # config set to no expiration
        gbl.invalidate_bin_counts.reset_mock()
        with mock.patch.dict('forgetracker.model.ticket.tg_config', **{'forgetracker.bin_cache_expire': 0}):
            gbl._bin_counts_expire = now - timedelta(minutes=5)
            bin = gbl.bin_count('qux')
            assert not gbl.invalidate_bin_counts.called

        # no expire value (e.g. from previously having config set to no expirations)
        gbl.invalidate_bin_counts.reset_mock()
        gbl._bin_counts_expire = None
        bin = gbl.bin_count('qux')
        assert bin['hits'] == 0
        assert gbl.invalidate_bin_counts.called

    @mock.patch('forgetracker.tasks.update_bin_counts')
    @mock.patch('forgetracker.model.ticket.datetime')
    def test_invalidate_bin_counts(self, mock_dt, mock_task):
        now = datetime.utcnow().replace(microsecond=0)
        mock_dt.utcnow.return_value = now
        gbl = Globals()

        # invalidated recently, don't dog-pile
        gbl._bin_counts_invalidated = now - timedelta(minutes=1)
        gbl.invalidate_bin_counts()
        assert not mock_task.post.called

        # invalidated too long ago, call again
        gbl._bin_counts_invalidated = now - timedelta(minutes=6)
        gbl.invalidate_bin_counts()
        assert mock_task.post.called
        assert gbl._bin_counts_invalidated == now

        # never invalidated
        mock_task.reset_mock()
        gbl._bin_counts_invalidated = None
        gbl.invalidate_bin_counts()
        assert mock_task.post.called
        assert gbl._bin_counts_invalidated == now

    @mock.patch('forgetracker.model.ticket.Bin')
    @mock.patch('forgetracker.model.ticket.search_artifact')
    @mock.patch('forgetracker.model.ticket.datetime')
    def test_update_bin_counts(self, mock_dt, mock_search, mock_bin):
        now = datetime.utcnow().replace(microsecond=0)
        mock_dt.utcnow.return_value = now
        gbl = Globals()
        gbl._bin_counts_invalidated = now - timedelta(minutes=1)
        mock_bin.query.find.return_value = [
            mock.Mock(summary='foo', terms='bar')]
        mock_search().hits = 5

        assert gbl._bin_counts_data == []  # sanity pre-check
        gbl.update_bin_counts()
        assert mock_bin.query.find.called
        mock_search.assert_called_with(
            forgetracker.model.Ticket, 'bar', rows=0, short_timeout=False, fq=['-deleted_b:true'])
        assert gbl._bin_counts_data == [{'summary': 'foo', 'hits': 5}]
        assert gbl._bin_counts_expire == now + timedelta(minutes=60)
        assert gbl._bin_counts_invalidated is None

    def test_append_new_labels(self):
        gbl = Globals()
        assert gbl.append_new_labels([], ['tag1']) == ['tag1']
        assert (
            gbl.append_new_labels(['tag1', 'tag2'], ['tag2']) == ['tag1', 'tag2'])
        assert gbl.append_new_labels(
            ['tag1', 'tag2'], ['tag3']) == ['tag1', 'tag2', 'tag3']
        assert gbl.append_new_labels(
            ['tag1', 'tag2', 'tag3'], ['tag2']) == ['tag1', 'tag2', 'tag3']


class TestCustomFields(TrackerTestWithModel):

    def test_it_has_sortable_custom_fields(self):
        tracker_globals = globals_with_custom_fields(
            [dict(label='Iteration Number',
                  name='_iteration_number',
                  show_in_search=False),
             dict(label='Point Estimate',
                  name='_point_estimate',
                  show_in_search=True)])
        expected = [dict(sortable_name='_point_estimate_s',
                         name='_point_estimate',
                         label='Point Estimate')]
        assert tracker_globals.sortable_custom_fields_shown_in_search(
        ) == expected


def globals_with_custom_fields(custom_fields):
    c.app.globals.custom_fields = custom_fields
    ThreadLocalORMSession.flush_all()
    return c.app.globals
