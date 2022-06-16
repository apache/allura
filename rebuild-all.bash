#!/bin/bash

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

APPS=(Allura* *Forge*)

# the "${...-e}" magic is inspired by this stack exchange and turns a list into a oneline
# https://unix.stackexchange.com/a/445522
APPS_WITH_DASH_E="${APPS[@]/#/-e}"

# don't install ForgeSVN in a main command, since it often is not installable, and its optional
APPS_DASHE_NO_SVN="${APPS_WITH_DASH_E//-eForgeSVN/}"  # string replacement
pip install --no-index $APPS_DASHE_NO_SVN
main_ret=$?

pip install --no-index -e ForgeSVN
if [ "$?" -gt 0 ]; then
  echo -e "\nIt is okay that ForgeSVN failed.  It needs pysvn which can be difficult to install."
  echo "You can ignore this error.  If you do want SVN support, see install_each_step.rst notes about SVN."
fi

exit $main_ret
