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

import ew
from ew import jinja2_ew
from allura.lib import validators as v

from forgetracker import model


class BinForm(ew.SimpleForm):
    template = 'jinja:forgetracker:templates/tracker_widgets/bin_form.html'
    defaults = dict(
        ew.SimpleForm.defaults,
        submit_text="Save Bin")

    class hidden_fields(ew.NameList):
        _id = jinja2_ew.HiddenField(
            validator=v.Ming(model.Bin), if_missing=None)

    class fields(ew.NameList):
        summary = jinja2_ew.TextField(
            label='Bin Name',
            validator=v.UnicodeString(not_empty=True))
        terms = jinja2_ew.TextField(
            label='Search Terms',
            validator=v.UnicodeString(not_empty=True))
