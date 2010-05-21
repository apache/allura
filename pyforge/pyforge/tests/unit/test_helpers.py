from unittest import TestCase

from mock import patch

from datetime import datetime
from pyforge.lib import helpers


class TestAgo:
    def setUp(self):
        self.start_time = datetime(2010, 1, 1, 0, 0, 0)

    def test_that_empty_times_are_phrased_in_minutes(self):
        self.assertTimeSince('0 minutes ago', 2010, 1, 1, 0, 0, 0)

    def test_that_partial_minutes_are_rounded(self):
        self.assertTimeSince('less than 1 minute ago', 2010, 1, 1, 0, 0, 29)
        self.assertTimeSince('1 minute ago', 2010, 1, 1, 0, 0, 31)

    def test_that_minutes_are_rounded(self):
        self.assertTimeSince('1 minute ago', 2010, 1, 1, 0, 1, 29)
        self.assertTimeSince('2 minutes ago', 2010, 1, 1, 0, 1, 31)

    def test_that_hours_are_rounded(self):
        self.assertTimeSince('1 hour ago', 2010, 1, 1, 1, 29, 0)
        self.assertTimeSince('2 hours ago', 2010, 1, 1, 1, 31, 0)

    def test_that_days_are_rounded(self):
        self.assertTimeSince('1 day ago', 2010, 1, 2, 11, 0, 0)
        self.assertTimeSince('2 days ago', 2010, 1, 2, 13, 0, 0)

    def test_that_months_are_rounded(self):
        # WebHelpers is kind of insane here - it rounds "1 month and 8 days"
        # to "one month", but "1 month and 9 days" to "two months". If the 8/9
        # distinction in this test ever breaks, that was fixed, and updating
        # this test is OK.
        self.assertTimeSince('1 month ago', 2010, 2, 8, 0, 0, 0)
        self.assertTimeSince('2 months ago', 2010, 2, 9, 0, 0, 0)
        self.assertTimeSince('2 months ago', 2010, 2, 20, 0, 0, 0)

    def test_that_years_are_rounded(self):
        self.assertTimeSince('1 year ago', 2011, 6, 1, 0, 0, 0)
        self.assertTimeSince('2 years ago', 2011, 8, 1, 0, 0, 0)

    def assertTimeSince(self, time_string, *time_components):
        assert time_string == self.time_since(*time_components)

    def time_since(self, *time_components):
        end_time = datetime(*time_components)
        with patch('pyforge.lib.helpers.datetime') as datetime_class:
            datetime_class.utcnow.return_value = end_time
            return helpers.ago(self.start_time)

