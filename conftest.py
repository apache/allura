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
import pytest

# should get rid of this once this issue is fixed https://github.com/TurboGears/tg2/issues/136
@pytest.fixture(autouse=True, scope='session')
def tg_context_patch():
    from tg import (
        request as r,
        tmpl_context as c,
        app_globals as g,
        cache,
        response,
        translator,
        url,
        config,
    )
    for marker in ('_is_coroutine', '_is_coroutine_marker'):
        r.__dict__[marker] = False
        c.__dict__[marker] = False
        g.__dict__[marker] = False
        cache.__dict__[marker] = False
        response.__dict__[marker] = False
        translator.__dict__[marker] = False
        url.__dict__[marker] = False
        config.__dict__[marker] = False
