import mock
from nose.tools import assert_equal
from datetime import datetime, timedelta

import forgetracker
from forgetracker.model import Globals
from forgetracker.tests.unit import TrackerTestWithModel
from pylons import c
from allura.lib import helpers as h

from ming.orm.ormsession import ThreadLocalORMSession


class TestGlobalsModel(TrackerTestWithModel):
    def setUp(self):
        super(TestGlobalsModel, self).setUp()
        c.project.install_app('Tickets', 'doc-bugs')
        ThreadLocalORMSession.flush_all()

    def test_it_has_current_tracker_globals(self):
        bugs_globals = Globals.query.get(app_config_id=c.app.config._id)
        assert c.app.globals == bugs_globals
        h.set_context('test', 'doc-bugs', neighborhood='Projects')
        assert c.app.globals != bugs_globals

    def test_next_ticket_number_increments(self):
        assert Globals.next_ticket_num() == 1
        assert Globals.next_ticket_num() == 2

    def test_ticket_numbers_are_independent(self):
        assert Globals.next_ticket_num() == 1
        h.set_context('test', 'doc-bugs', neighborhood='Projects')
        assert Globals.next_ticket_num() == 1

    @mock.patch('forgetracker.model.ticket.datetime')
    def test_bin_count(self, mock_dt):
        now = datetime.utcnow()
        mock_dt.utcnow.return_value = now
        gbl = Globals()
        gbl._bin_counts_data = [{'summary': 'foo', 'hits': 1}, {'summary': 'bar', 'hits': 2}]
        gbl.invalidate_bin_counts = mock.Mock()

        # not expired, finds bin
        gbl._bin_counts_expire = now + timedelta(minutes=5)
        bin = gbl.bin_count('bar')
        assert_equal(bin['hits'], 2)
        assert not gbl.invalidate_bin_counts.called

        # expired, returns value for missing bin
        gbl._bin_counts_expire = now - timedelta(minutes=5)
        bin = gbl.bin_count('qux')
        assert_equal(bin['hits'], 0)
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
        assert_equal(gbl._bin_counts_invalidated, now)

        # never invalidated
        mock_task.reset_mock()
        gbl._bin_counts_invalidated = None
        gbl.invalidate_bin_counts()
        assert mock_task.post.called
        assert_equal(gbl._bin_counts_invalidated, now)

    @mock.patch('forgetracker.model.ticket.Bin')
    @mock.patch('forgetracker.model.ticket.search_artifact')
    @mock.patch('forgetracker.model.ticket.datetime')
    def test_update_bin_counts(self, mock_dt, mock_search, mock_bin):
        now = datetime.utcnow().replace(microsecond=0)
        mock_dt.utcnow.return_value = now
        gbl = Globals()
        gbl._bin_counts_invalidated = now - timedelta(minutes=1)
        mock_bin.query.find.return_value = [mock.Mock(summary='foo', terms='bar')]
        mock_search().hits = 5

        assert_equal(gbl._bin_counts_data, [])  # sanity pre-check
        gbl.update_bin_counts()
        assert mock_bin.query.find.called
        mock_search.assert_called_with(forgetracker.model.Ticket, 'bar', rows=0, short_timeout=False)
        assert_equal(gbl._bin_counts_data, [{'summary': 'foo', 'hits': 5}])
        assert_equal(gbl._bin_counts_expire, now + timedelta(minutes=60))
        assert_equal(gbl._bin_counts_invalidated, None)


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
        assert tracker_globals.sortable_custom_fields_shown_in_search() == expected


def globals_with_custom_fields(custom_fields):
    c.app.globals.custom_fields = custom_fields
    ThreadLocalORMSession.flush_all()
    return c.app.globals

