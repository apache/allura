#!/bin/bash
# need to specify the shell, else Jenkins will quit after the first non-zero exit

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

IMAGE_TAG=allura

echo
echo "============================================================================="
echo "Jenkins Host Info:"
echo "============================================================================="
echo -n 'cpu count: '; grep -c processor /proc/cpuinfo 
echo hostname: `hostname --short`
echo whoami: `whoami`
echo NODE_NAME: $NODE_NAME
echo docker: `docker version`
echo docker compose: `docker-compose version`
echo path: $PATH
echo workspace: $WORKSPACE
echo jenkins_home: $JENKINS_HOME
echo home: $HOME
echo pwd: `pwd`
env

echo
echo "============================================================================="
echo "Run: cleanup previous runs"
echo "============================================================================="
rm -rf ./allura-data
git clean -f -x  # remove test.log, pytest.junit.xml etc (don't use -d since it'd remove our venv dir)

docker-compose down

echo
echo "============================================================================="
echo "Run: build docker image"
echo "============================================================================="
docker-compose build

echo
echo "============================================================================="
echo "Setup: venv, pip, pysvn, ./rebuild-all.sh, npm, etc."
echo "============================================================================="
docker-compose run web scripts/init-docker-dev.sh

echo
echo "============================================================================="
echo "Starting up docker containers"
echo "============================================================================="
docker-compose up -d web

echo
echo "============================================================================="
echo "Docker Container Info:"
echo "============================================================================="
docker-compose exec -T web bash -c '
echo python path: `which python; python -V`;
echo python3.7 path: `which python3.7; python3.7 -V`;
git --version;
svn --version;
echo pip: `pip3 --version`;
echo npm: `npm --version`;
echo whoami: `whoami`;
'

echo
echo "============================================================================="
echo "Setup: tests"
echo "============================================================================="
# set up test dependencies
docker-compose exec -T web pip install -q -r requirements-dev.txt

# make test git repos safe to run even though owned by different user
docker-compose exec -T web chown root:root -R /allura

echo
echo "============================================================================="
echo "Run: tests"
echo "============================================================================="

# use "Allura* Forge* scripts" instead of "." so that .allura-venv doesn't get checked too (and '.' gives './' prefixed results which don't work out)
docker-compose exec -T web bash -c "pyflakes Allura* Forge* scripts | awk -F\: '{printf \"%s:%s: [E]%s\n\", \$1, \$2, \$3}' > pyflakes.txt"
docker-compose exec -T web bash -c "pycodestyle Allura* Forge* scripts > pep8.txt"

# TODO: ALLURA_VALIDATION=all
docker-compose exec -T -e LANG=en_US.UTF-8 web ./run_tests --junit-xml=pytest.junit.xml # --with-coverage --cover-erase
retcode=$?

#find . -name .coverage -maxdepth 2 | while read coveragefile; do pushd `dirname $coveragefile`; coverage xml --include='forge*,allura*'; popd; done;

echo
echo "============================================================================="
echo "Shutdown"
echo "============================================================================="
docker-compose down
docker container prune -f
docker volume prune -f

exit $retcode