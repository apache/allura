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

import ew as ew_core
import ew.jinja2_ew as ew
from formencode import validators as fev

from allura.lib import validators as V

from .form_fields import AutoResizeTextarea
from .forms import ForgeForm


class OAuthApplicationForm(ForgeForm):
    submit_text = 'Register new application'
    style = 'wide'

    class fields(ew_core.NameList):
        application_name = ew.TextField(label='Application Name',
                                        validator=V.UniqueOAuthApplicationName(),
                                        attrs=dict(
                                            required=True,
                                        ),
                                        )
        application_description = AutoResizeTextarea(
            label='Application Description')


class OAuthRevocationForm(ForgeForm):
    submit_text = 'Revoke Access'
    fields = []

    class fields(ew_core.NameList):
        _id = ew.HiddenField()


class OAuth2ApplicationForm(ForgeForm):
    submit_text = 'Register new Application'
    style = 'wide'

    class fields(ew_core.NameList):
        application_name = ew.TextField(label='Application Name',
                                        validator=V.UnicodeString(not_empty=True),
                                        attrs=dict(
                                            required=True,
                                        ),
                                        )
        application_description = AutoResizeTextarea(label='Application Description')

        # SortableRepeatedField would be nice to use (and ignore sorting) so you can add many dynamically,
        # but couldn't get it to work easily
        redirect_url_1 = ew.TextField(
            label='Redirect URL(s)',
            validator=fev.URL(not_empty=True),
            attrs=dict(type='url', style='min-width:25em', required=True),
        )
        redirect_url_2 = ew.TextField(
            validator=fev.URL(),
            attrs=dict(type='url', style='min-width:25em; margin-left: 162px;'),  # match grid-4 label width
        )
        redirect_url_3 = ew.TextField(
            validator=fev.URL(),
            attrs=dict(type='url', style='min-width:25em; margin-left: 162px;'),  # match grid-4 label width
        )

