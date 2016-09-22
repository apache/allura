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

from ...github import tasks


@mock.patch.object(tasks, 'GitHubProjectExtractor')
@mock.patch.object(tasks, 'ThreadLocalORMSession')
@mock.patch.object(tasks, 'c')
@mock.patch.object(tasks, 'g', mock.MagicMock())
def test_import_project_info(c, session, ghpe):
    c.project = mock.Mock(name='project')
    c.user = mock.Mock(name='user')
    tasks.import_project_info('my-project')
    ghpe.assert_called_once_with('my-project', user=c.user)
    ghpe.return_value.get_summary.assert_called_once_with()
    ghpe.return_value.get_homepage.assert_called_once_with()
    session.flush_all.assert_called_once_with()
