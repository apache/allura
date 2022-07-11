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


class ValidateSvnUrl(validators.URLIsPrivate):
    url_re = re.compile(r'''
        ^(http|https|svn)://
        (?:[%:\w]*@)?                              # authenticator
        (?:                                        # ip or domain
        (?P<ip>(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))|
        (?P<domain>[a-z0-9][a-z0-9\-]{,62}\.)*     # subdomain
        (?P<tld>[a-z]{2,63}|xn--[a-z0-9\-]{2,59})  # top level domain
        )
        (?::[0-9]{1,5})?                           # port
        # files/delims/etc
        (?P<path>/[a-z0-9\-\._~:/\?#\[\]@!%\$&\'\(\)\*\+,;=]*)?
        $
    ''', re.I | re.VERBOSE)

    def _to_python(self, value, state):
        value = super()._to_python(value, state)
        if 'plugins.svn.wordpress.org' in value:
            raise fev.Invalid("That SVN repo is to large to import from.", value, state)
        return value


class ImportForm(ForgeForm):
    submit_text = 'Import'

    class fields(ew_core.NameList):
        checkout_url = ew.TextField(
            label='Checkout URL',
            validator=ValidateSvnUrl(not_empty=True), attrs=dict(size=65))
