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

from tg import tmpl_context as c
from ming.orm.ormsession import ThreadLocalORMSession

from allura.websetup import bootstrap
from allura.lib import helpers as h
from allura.lib import plugin
from allura import model as M
from alluratest.controller import setup_basic_test


def setup_module():
    setup_basic_test()


class FilesTestWithModel:

    def setup_method(self, method):
        bootstrap.wipe_database()
        project_reg = plugin.ProjectRegistrationProvider.get()
        c.user = bootstrap.create_user('Test User')
        neighborhood = M.Neighborhood(name='Projects', url_prefix='/p/',
                                      features=dict(private_projects=False,
                                                    max_projects=None,
                                                    css='none',
                                                    google_analytics=False))
        project_reg.register_neighborhood_project(neighborhood, [c.user])
        c.project = neighborhood.register_project('test', c.user)
        c.project.install_app('Files', 'files')
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'files', neighborhood='Projects')

    def teardown_method(self, method):
        ThreadLocalORMSession.close_all()

