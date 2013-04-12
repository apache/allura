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

from mock import Mock
from allura.controllers.base import DispatchIndex, BaseController


def test_dispatch_index():
    controller = Mock(BaseController)
    d = DispatchIndex()
    d._lookup = lambda self, *remainder: (controller, remainder)

    d.dispatcher = Mock()
    state = Mock()
    d._dispatch(state, ['index'])
    state.add_controller.assert_called_with('BaseController', controller)
    d.dispatcher._dispatch.assert_called_with(state, ())

    state = Mock()
    d._dispatch(state, ['index', 'next'])
    state.add_controller.assert_called_with('BaseController', controller)
    d.dispatcher._dispatch.assert_called_with(state, ('next', ))

    state = Mock()
    d._dispatch(state, ['index2'])
    assert not state.add_controller.called
    d.dispatcher._dispatch.assert_called_with(state, ['index2'])
