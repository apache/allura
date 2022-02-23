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

from ast import literal_eval

from allura.command import base

from bson import ObjectId
from allura import model as M
from allura.lib import exceptions
from ming.orm import session

# Example usage:
# paster set-neighborhood-features development.ini
# 4f50c898610b270c92000286 max_projects 50


class SetNeighborhoodFeaturesCommand(base.Command):
    min_args = 4
    max_args = 4
    usage = "<ini file> <neighborhood> <feature> <value>"
    summary = "Change the neighborhood features\r\n" \
        "\t<neighborhood> - the neighborhood name or object id\r\n" \
        "\t<feature> - feature value to change options are max_projects, css, google_analytics, or private_projects\r\n" \
        "\t<value> - value to give the feature - see below for descriptions\r\n" \
        "\t    max_projects - maximum projects allowed in neighborhood - specify None for no limit\r\n" \
        "\t    css - type of css customization - use \"none\", \"picker\", or \"custom\".\r\n" \
        "\t    google_analytics - allow the user to use google analytics - True or False\r\n" \
        "\t    private_projects - allow private projects in the neighborhood - True or False"
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        n_id = self.args[1]
        n_feature = self.args[2]
        # try to get a bool or int val, otherwise treat it as a string
        try:
            n_value = literal_eval(self.args[3])
        except ValueError:
            n_value = self.args[3]
        if n_feature not in ["max_projects", "css", "google_analytics", "private_projects"]:
            raise exceptions.NoSuchNBFeatureError("%s is not a valid "
                                                  "neighborhood feature. The valid features are \"max_projects\", "
                                                  "\"css\", \"google_analytics\" and \"private_projects\"" % n_feature)

        n = M.Neighborhood.query.get(name=n_id)
        if not n:
            n = M.Neighborhood.query.get(_id=ObjectId(n_id))

        if not n:
            raise exceptions.NoSuchNeighborhoodError("The neighborhood %s "
                                                     "could not be found in the database" % n_id)
        else:
            if n_feature == "max_projects":
                if isinstance(n_value, int) or n_value is None:
                    n.features['max_projects'] = n_value
                else:
                    raise exceptions.InvalidNBFeatureValueError("max_projects must be "
                                                                "an int or None.")
            elif n_feature == "css":
                if n_value in ['none', 'custom', 'picker']:
                    n.features['css'] = n_value
                else:
                    raise exceptions.InvalidNBFeatureValueError("css must be "
                                                                "'none', 'custom', or 'picker'")
            elif n_feature == "google_analytics":
                if isinstance(n_value, bool):
                    n.features['google_analytics'] = n_value
                else:
                    raise exceptions.InvalidNBFeatureValueError("google_analytics must be "
                                                                "a boolean")
            else:
                if isinstance(n_value, bool):
                    n.features['private_projects'] = n_value
                else:
                    raise exceptions.InvalidNBFeatureValueError("private_projects must be "
                                                                "a boolean")
            session(M.Neighborhood).flush()
