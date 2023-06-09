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

PKGDIR=$(python -c 'from distutils import sysconfig; print(sysconfig.get_python_lib())')

function rebuild() {
    local DIR=$1
    echo "# setting up $DIR"
    pushd $DIR > /dev/null
    if [ -d *.egg-info ] && [[ $(find *.egg-info ! -newer setup.py | grep -v zip-safe) == "" ]]; then
        # as long as there's .egg-info directory around, and all are newer than setup.py
        # we can do a quick and dirty replacement of `pip install -e`
        # its so much faster, but misses the `python setup.py egg_info` part (entry points and other distribution info)
        echo -e -n "$(pwd -P)\n." > $PKGDIR/$(basename $(pwd -P)).egg-link
        grep -q $(pwd -P) $PKGDIR/easy-install.pth || pwd -P >> $PKGDIR/easy-install.pth  # if path is not in this file, append
    else
        # full proper installation
        pip install -e .
    fi
    popd > /dev/null
}

for APP in Allura* *Forge*
do
    rebuild $APP
done
