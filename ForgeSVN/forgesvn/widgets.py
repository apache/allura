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

import re

import ew as ew_core
import ew.jinja2_ew as ew
from formencode import validators as fev

from allura.lib import validators
from allura.lib.widgets.forms import ForgeForm


class ValidateSvnUrl(validators.NonPrivateUrl):
    def __init__(self, *args, **kw):
        super().__init__(*args, enforce_schemes=['svn', 'http', 'https'], **kw)

    def _convert_to_python(self, value, state):
        value = super()._convert_to_python(value, state)
        if 'plugins.svn.wordpress.org' in value:
            raise fev.Invalid("That SVN repo is to large to import from.", value, state)
        return value


class ImportForm(ForgeForm):
    submit_text = 'Import'

    class fields(ew_core.NameList):
        checkout_url = ew.TextField(
            label='Checkout URL',
            validator=ValidateSvnUrl(not_empty=True), attrs=dict(size=65))
