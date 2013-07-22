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

import datetime
import tempfile
import json
import operator

from nose.tools import assert_equal

from allura import model as M
from allura.tests import decorators as td
from forgetracker import model as TM
from forgetracker.tests.functional.test_root import TrackerTestController


class TestBulkExport(TrackerTestController):
    @td.with_tracker
    def setup_with_tools(self):
        super(TestBulkExport, self).setup_with_tools()
        self.project = M.Project.query.get(shortname='test')
        self.tracker = self.project.app_instance('bugs')
        self.new_ticket(summary='foo', _milestone='1.0')

    def test_bulk_export(self):
        f = tempfile.TemporaryFile()
        self.tracker.bulk_export(f)
        f.seek(0)
        tracker = json.loads(f.read())
        #tickets = sorted(tracker['tickets'], key=operator.itemgetter('title'))
        tickets = tracker['tickets']
        print tickets
        assert_equal(len(tickets), 1)
