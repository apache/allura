#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

#!/bin/bash
set -euo pipefail

BASEDIR=$(dirname "$0")
ALLURA_DIR=$(realpath "$BASEDIR/../../Allura")
cd "$ALLURA_DIR"

# get INI from environment or prompt for input:
INI=${INI:-}
if [ -z "$INI" ]; then
    read -rp "Enter the path to the Allura INI file (or provide as env var): " INI
fi

paster script $INI ../scripts/convert_encrypted_field.py -- --remove-unencrypted forgediscussion.model.forum.Forum monitoring_email
