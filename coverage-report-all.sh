#!/bin/sh
#
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
#
# This script calculates global codebase coverage, based on coverage
# of individual application packages.
#

DIRS="Allura Forge*"
EXCLUDES='*/migrations*,*/ez_setup/*,*allura/command/*'

for dir in $DIRS; do
    if [ ! -f $dir/.coverage ]; then
        echo "$dir/.coverage not found - please run ./run_test --with-coverage first"
    else
        ln -sf $dir/.coverage .coverage.$dir
    fi
done

coverage combine
coverage report --ignore-errors --include='Allura/*,Forge*' --omit=$EXCLUDES

if [ "$1" = "--html" ]; then
    coverage html --ignore-errors --include='Allura/*,Forge*' --omit=$EXCLUDES -d report.coverage
    coverage html --ignore-errors --include='Allura/*' --omit=$EXCLUDES -d Allura.coverage
fi
