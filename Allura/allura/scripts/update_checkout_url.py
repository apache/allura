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

"""
Find repos with blank checkout url and top-level "trunk" dir,
and point checkout_url at trunk.
"""

import logging

from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils
from allura.scripts import ScriptTask

from forgesvn.model.svn import Repository, svn_path_exists

log = logging.getLogger(__name__)


class UpdateCheckoutUrl(ScriptTask):

    @classmethod
    def execute(cls, options):
        query = {'tool_name': {'$regex': '^svn$', '$options': 'i'},
                 'options.checkout_url': ''}
        for chunk in utils.chunked_find(M.AppConfig, query):
            for config in chunk:
                repo = Repository.query.get(app_config_id=config._id)
                trunk_path = "file://{0}{1}/trunk".format(repo.fs_path,
                                                          repo.name)
                if svn_path_exists(trunk_path):
                    config.options['checkout_url'] = "trunk"
                    log.info("Update checkout_url for: %s", trunk_path)
            ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    UpdateCheckoutUrl.main()
