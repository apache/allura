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

import logging
import re

from tg import tmpl_context as c

from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils
from forgewiki import model as WM

log = logging.getLogger(__name__)

default_description = r'^\s*(?:You can edit this description in the admin page)?\s*$'

default_personal_project_tmpl = ("This is the personal project of %s."
                                 " This project is created automatically during user registration"
                                 " as an easy place to store personal data that doesn't need its own"
                                 " project such as cloned repositories.\n\n%s")


def main():
    users = M.Neighborhood.query.get(name='Users')
    for chunk in utils.chunked_find(M.Project, {'neighborhood_id': users._id}):
        for p in chunk:
            user = p.user_project_of
            if not user:
                continue

            description = p.description
            if description is None or re.match(default_description, description):
                continue

            app = p.app_instance('wiki')
            if app is None:
                try:
                    app = p.install_app('wiki')
                except Exception as e:
                    log.error("Unable to install wiki for user %s: %s" %
                              (user.username, str(e)))
                    continue

            page = WM.Page.query.get(
                app_config_id=app.config._id, title='Home')
            if page is None:
                continue

            c.app = app
            c.project = p
            c.user = user

            if "This is the personal project of" in page.text:
                if description not in page.text:
                    page.text = f"{page.text}\n\n{description}"
                    log.info("Update wiki home page text for %s" %
                             user.username)
            elif "This is the default page" in page.text:
                page.text = default_personal_project_tmpl % (
                    user.display_name, description)
                log.info("Update wiki home page text for %s" % user.username)
            else:
                pass

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
