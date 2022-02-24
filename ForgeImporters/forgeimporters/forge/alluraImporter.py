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

import os
import json

from forgeimporters.base import (
    ToolImporter,
    get_importer_upload_path,
)

from allura import model as M


class AlluraImporter(ToolImporter):

    def get_user(self, username):
        if username is None:
            return M.User.anonymous()
        user = M.User.by_username(username)
        if not user:
            user = M.User.anonymous()
        return user

    def annotate(self, text, user, username, label=''):
        if username is not None \
           and user is not None \
           and user.is_anonymous() \
           and username != "" \
           and username != 'nobody' \
           and username != '*anonymous':
            return f'*Originally{label} by:* {username}\n\n{text}'

        if text is None:
            text = ""

        return text

    def _load_json_by_filename(self, project, filename):
        upload_path = get_importer_upload_path(project)
        full_path = os.path.join(upload_path, filename)
        with open(full_path) as fp:
            return json.load(fp)
