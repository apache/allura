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

import sys

from allura.app import Application
from allura.lib.decorators import task
from allura.lib.exceptions import CompoundError


class ThemeProviderTestApp(Application):
    """
    If this test class is added directly to a test module, pkg_resources internals
    will throw this error:
        NotImplementedError: Can't perform this operation for unregistered loader type
    This is because pytest adds a hook to override the default assert behavior and this
    conflicts/messes-with pkg_resources. Theoretically on python > py37, importlib.resources
    can do the same things as pkg_resources and faster, but those solutions don't currently
    work on py37.
    """
    icons = {
        24: 'images/testapp_24.png',
    }


@task
def raise_compound_exception():
    errs = []
    for x in range(10):
        try:
            assert False, 'assert %d' % x
        except Exception:
            errs.append(sys.exc_info())
    raise CompoundError(*errs)