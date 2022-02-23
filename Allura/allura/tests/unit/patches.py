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

from mock import Mock, patch, MagicMock
from tg import tmpl_context as c

from allura.tests.unit.factories import (
    create_project,
    create_app_config,
    create_user,
)


def fake_app_patch(test_case):
    project = create_project('myproject')
    app_config = create_app_config(project, 'my_app')
    app = Mock()
    app.__version__ = '0'
    app.config = app_config
    app.url = '/-app-/'
    return patch.object(c, 'app', app, create=True)


def fake_user_patch(test_case):
    user = create_user(username='my_user')
    return patch.object(c, 'user', user, create=True)


def project_app_loading_patch(test_case):
    test_case.fake_app = Mock()
    test_case.project_app_instance_function = Mock()
    test_case.project_app_instance_function.return_value = test_case.fake_app

    return patch('allura.model.project.Project.app_instance',
                 test_case.project_app_instance_function)


def disable_notifications_patch(test_case):
    return patch('allura.model.notification.Notification.post')


def fake_redirect_patch(test_case):
    return patch('allura.controllers.discuss.redirect')


def fake_request_patch(test_case):
    return patch('allura.controllers.discuss.request',
                 MagicMock(
                     referer='.'
                 ))
