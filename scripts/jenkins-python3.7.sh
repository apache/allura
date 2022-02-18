#!/bin/bash
# need to specify the shell, else Jenkins will quit after the first non-zero exit

# *****************************************************************************
# DO NOT MODIFY ON JENKINS
#   This file is maintained in allura/scripts/jenkins-python3.7sh
# *****************************************************************************

IMAGE_TAG=allura

echo
echo "============================================================================="
echo "Jenkins Host Info:"
echo "============================================================================="
echo -n 'cpu count: '; grep -c processor /proc/cpuinfo 
echo hostname: `hostname --short`
echo NODE_NAME: $NODE_NAME
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
git clean -f -x  # remove test.log, nosetest.xml etc (don't use -d since it'd remove our venv dir)

echo
echo "============================================================================="
echo "Run: build docker image"
echo "============================================================================="
docker-compose build

echo
echo "============================================================================="
echo "Docker Container Info:"
echo "============================================================================="
docker-compose run web bash -c '
echo python path: `which python; python -V`;
echo python3.7 path: `which python3.7; python3.7 -V`;
git --version;
svn --version;
echo pip: `pip3 --version`;
echo npm: `npm --version`;'

echo
echo "============================================================================="
echo "Setup: venv, pip, pysvn, ./rebuild-all.sh, npm, etc."
echo "============================================================================="
docker-compose run web scripts/init-docker-dev.sh

echo
echo "============================================================================="
echo "Setup: tests"
echo "============================================================================="
# set up test dependencies
docker-compose run web pip install -r requirements-dev.txt

echo
echo "============================================================================="
echo "Run: tests"
echo "============================================================================="

# use "Allura* Forge* scripts" instead of "." so that .allura-venv doesn't get checked too (and '.' gives './' prefixed results which don't work out)
docker-compose run web pyflakes Allura* Forge* scripts | awk -F\: '{printf "%s:%s: [E]%s\n", $1, $2, $3}' > pyflakes.txt
docker-compose run web pycodestyle Allura* Forge* scripts > pep8.txt

# TODO: ALLURA_VALIDATION=all
docker-compose run -e LANG=en_US.UTF-8 web ./run_tests --with-xunitmp # --with-coverage --cover-erase
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