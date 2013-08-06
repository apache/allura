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

import mock

from ...google import tasks


@mock.patch.object(tasks, 'GoogleCodeProjectExtractor')
@mock.patch.object(tasks, 'ThreadLocalORMSession')
@mock.patch.object(tasks, 'c')
def test_import_project_info(c, session, gpe):
    c.project = mock.Mock(name='project')
    tasks.import_project_info('my-project')
    gpe.assert_called_once_with(c.project, 'my-project', 'project_info')
    gpe.return_value.get_short_description.assert_called_once_with()
    gpe.return_value.get_icon.assert_called_once_with()
    gpe.return_value.get_license.assert_called_once_with()
    session.flush_all.assert_called_once_with()
