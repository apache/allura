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

from ming.orm.ormsession import ThreadLocalORMSession

from tg import tmpl_context as c

from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.widgets import ticket_form


class TestTicketForm(TrackerTestWithModel):

    def test_it_creates_status_field(self):
        g = c.app.globals
        g.open_status_names = 'open'
        g.closed_status_names = 'closed'
        ThreadLocalORMSession.flush_all()
        assert self.options_for_field('status')() == ['open', 'closed']

    def options_for_field(self, field_name):
        fields = ticket_form.TicketForm().fields
        matching_fields = [field
                           for field in fields
                           if field.name == field_name]
        return matching_fields[0].options
