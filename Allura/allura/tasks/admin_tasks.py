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

import inspect

from tg import tmpl_context as c

from allura import model as M
from allura.lib.decorators import task


@task
def install_app(*args, **kwargs):
    """Install an application directly onto c.project, bypassing the UI and
    any app constraints like ``installable=False``.

    """
    c.project.install_app(*args, **kwargs)

install_app.__doc__ += '''
    Arguments::

        ''' + inspect.formatargspec(*inspect.getargspec(
    M.Project.install_app
)).replace('self, ', '')
