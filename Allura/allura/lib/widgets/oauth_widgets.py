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

from allura.lib import validators as V

from .form_fields import AutoResizeTextarea
from .forms import ForgeForm


REDIRECT_URL_FIELDS = ('redirect_url_1', 'redirect_url_2', 'redirect_url_3')


def add_redirect_url_fields(fields: ew_core.NameList) -> None:
    """Add the redirect URL fields shared by the OAuth1 and OAuth2 application forms.

    HttpsUrl prevents unencrypted http so tokens can't be intercepted.  In theory could allow some
    other protocols (but not http:) so it can work with mobile apps etc.
    """
    for i, field_name in enumerate(REDIRECT_URL_FIELDS):
        first = i == 0
        attrs = dict(type='url', pattern='https://.*', title='must start with https://',
                     # match grid-4 label width for the ones with no label
                     style='min-width:25em' if first else 'min-width:25em; margin-left: 162px;')
        kwargs = {}
        if first:
            attrs.update(placeholder='https://...', required=True)
            kwargs['label'] = 'Redirect URL(s)'
        field = ew.TextField(validator=V.HttpsUrl(not_empty=first), attrs=attrs, **kwargs)
        field.name = field_name  # set after construction, else ew derives a label from it for the unlabeled fields
        fields.append(field)


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

    add_redirect_url_fields(fields)


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

    add_redirect_url_fields(fields)
