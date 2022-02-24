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

from . import base

from ming.orm import session
from bson import ObjectId

from allura import model as M
from allura.lib import plugin, exceptions

log = logging.getLogger(__name__)


class CreateNeighborhoodCommand(base.Command):
    min_args = 3
    max_args = None
    usage = '<ini file> <neighborhood_shortname> <admin1> [<admin2>...]'
    summary = 'Create a new neighborhood with the listed admins'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        admins = [M.User.by_username(un) for un in self.args[2:]]
        shortname = self.args[1]
        n = M.Neighborhood(
            name=shortname,
            url_prefix='/' + shortname + '/',
            features=dict(private_projects=False,
                          max_projects=None,
                          css='none',
                          google_analytics=False))
        project_reg = plugin.ProjectRegistrationProvider.get()
        project_reg.register_neighborhood_project(n, admins)
        log.info(f'Successfully created neighborhood "{shortname}"')


class UpdateNeighborhoodCommand(base.Command):
    min_args = 3
    max_args = None
    usage = '<ini file> <neighborhood> <home_tool_active>'
    summary = 'Activate Home application for neighborhood\r\n' \
        '\t<neighborhood> - the neighborhood name or _id\r\n' \
        '\t<value> - boolean value to install/uninstall Home tool\r\n' \
        '\t    must be True or False\r\n\r\n' \
        '\tExample:\r\n' \
        '\tpaster update-neighborhood-home-tool development.ini Projects True'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        shortname = self.args[1]
        nb = M.Neighborhood.query.get(name=shortname)
        if not nb:
            nb = M.Neighborhood.query.get(_id=ObjectId(shortname))
        if nb is None:
            raise exceptions.NoSuchNeighborhoodError("The neighborhood %s "
                                                     "could not be found in the database" % shortname)
        tool_value = self.args[2].lower()
        if tool_value[:1] == "t":
            home_tool_active = True
        else:
            home_tool_active = False

        if home_tool_active == nb.has_home_tool:
            return

        p = nb.neighborhood_project
        if home_tool_active:
            zero_position_exists = False
            for ac in p.app_configs:
                if ac.options['ordinal'] == 0:
                    zero_position_exists = True
                    break

            if zero_position_exists:
                for ac in p.app_configs:
                    ac.options['ordinal'] = ac.options['ordinal'] + 1
            p.install_app('home', 'home', 'Home', ordinal=0)
        else:
            app_config = p.app_config('home')
            zero_position_exists = False
            if app_config.options['ordinal'] == 0:
                zero_position_exists = True

            p.uninstall_app('home')
            if zero_position_exists:
                for ac in p.app_configs:
                    ac.options['ordinal'] = ac.options['ordinal'] - 1

        session(M.AppConfig).flush()
        session(M.Neighborhood).flush()
