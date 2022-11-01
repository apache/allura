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

from datetime import datetime

from mock import patch

from allura.lib import helpers


class TestAgo:

    def setup_method(self, method):
        self.start_time = datetime(2010, 1, 1, 0, 0, 0)

    def test_that_exact_times_are_phrased_in_seconds(self):
        self.assertTimeSince('0 seconds ago', 2010, 1, 1, 0, 0, 0)

    def test_that_partial_seconds_are_rounded(self):
        self.assertTimeSince('less than 1 second ago', 2010, 1, 1, 0, 0, 0, 1)
        # the are not rounded, actually.  oh well
        self.assertTimeSince('less than 1 second ago', 2010, 1, 1, 0, 0, 0, 999999)
        # negative partial seconds don't say 'less than'
        self.assertTimeSince('in 1 second', 2009, 12, 31, 23, 59, 59, 1)
        self.assertTimeSince('in 1 second', 2009, 12, 31, 23, 59, 59, 999999)

    def test_that_minutes_are_rounded(self):
        self.assertTimeSince('1 minute ago', 2010, 1, 1, 0, 1, 29)
        self.assertTimeSince('2 minutes ago', 2010, 1, 1, 0, 1, 31)
        self.assertTimeSince('in 1 minute', 2009, 12, 31, 23, 58, 31)
        self.assertTimeSince('in 2 minutes', 2009, 12, 31, 23, 58, 29)

    def test_that_hours_are_rounded(self):
        self.assertTimeSince('1 hour ago', 2010, 1, 1, 1, 29, 0)
        self.assertTimeSince('2 hours ago', 2010, 1, 1, 1, 31, 0)
        self.assertTimeSince('in 1 hour', 2009, 12, 31, 22, 31, 0)
        self.assertTimeSince('in 2 hours', 2009, 12, 31, 22, 29, 0)

    def test_that_days_are_rounded(self):
        self.assertTimeSince('1 day ago', 2010, 1, 2, 11, 0, 0)
        self.assertTimeSince('2 days ago', 2010, 1, 2, 13, 0, 0)
        self.assertTimeSince('in 1 day', 2009, 12, 30, 13, 0, 0)
        self.assertTimeSince('in 2 days', 2009, 12, 30, 11, 0, 0)

    def test_that_days_do_not_show_after(self):
        self.assertTimeSince('7 days ago', 2010, 1, 8, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2010, 1, 8, 0, 0, 1)
        self.assertTimeSince('7 days ago', 2010, 1, 8, 11, 0, 0, show_date_after=8)
        self.assertTimeSince('8 days ago', 2010, 1, 8, 13, 0, 0, show_date_after=8)
        self.assertTimeSince('8 days ago', 2010, 1, 9, 0, 0, 0, show_date_after=8)
        self.assertTimeSince('2010-01-01', 2010, 1, 9, 0, 0, 1, show_date_after=8)

    def test_that_months_are_rounded(self):
        self.assertTimeSince('2010-01-01', 2010, 2, 8, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2010, 2, 9, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2010, 2, 20, 0, 0, 0)

        # the 9th is the rounding down cutoff for february /shrug
        self.assertTimeSince('1 month ago', 2010, 2, 1, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('1 month ago', 2010, 2, 8, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('2 months ago', 2010, 2, 9, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('2 months ago', 2010, 2, 20, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('2 months ago', 2010, 2, 28, 0, 0, 0, show_date_after=None)

        self.assertTimeSince('2010-01-01', 2009, 11, 24, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2009, 11, 23, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2009, 11, 1, 0, 0, 0)

        # the 24th is the rounding up cutoff for november /shrug
        self.assertTimeSince('in 1 month', 2009, 11, 30, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('in 1 month', 2009, 11, 24, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('in 2 months', 2009, 11, 23, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('in 2 months', 2009, 11, 1, 0, 0, 0, show_date_after=None)

    def test_that_years_are_rounded(self):
        self.assertTimeSince('2010-01-01', 2011, 6, 1, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2011, 8, 1, 0, 0, 0)
        self.assertTimeSince('1 year ago', 2011, 6, 1, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('2 years ago', 2011, 8, 1, 0, 0, 0, show_date_after=None)

        self.assertTimeSince('2010-01-01', 2008, 8, 1, 0, 0, 0)
        self.assertTimeSince('2010-01-01', 2008, 6, 1, 0, 0, 0)
        self.assertTimeSince('in 1 year', 2008, 8, 1, 0, 0, 0, show_date_after=None)
        self.assertTimeSince('in 2 years', 2008, 6, 1, 0, 0, 0, show_date_after=None)

    def assertTimeSince(self, time_string, *time_components, **kwargs):
        assert time_string == self.time_since(*time_components, **kwargs)

    def time_since(self, *time_components, **kwargs):
        end_time = datetime(*time_components)
        with patch('allura.lib.helpers.datetime') as datetime_class:
            datetime_class.utcnow.return_value = end_time
            return helpers.ago(self.start_time, **kwargs)
