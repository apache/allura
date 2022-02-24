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

from allura.lib.decorators import task, event_handler
from allura.lib.exceptions import CompoundError
import six


@task
def event(event_type, *args, **kwargs):
    exceptions = []
    for t in event_handler.listeners[event_type]:
        try:
            t(event_type, *args, **kwargs)
        except Exception:
            exceptions.append(sys.exc_info())
    if exceptions:
        if len(exceptions) == 1:
            raise exceptions[0][1].with_traceback(exceptions[0][2])
        else:
            raise CompoundError(*exceptions)
