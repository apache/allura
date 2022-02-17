#!/bin/bash
# need to specify the shell, else Jenkins will quit after the first non-zero exit

echo -n 'cpu count: '; grep -c processor /proc/cpuinfo 
echo python path: `which python; python -V`
echo python3 path: `which python3; python3 -V`
echo python3.7 path: `which python3.7;`
echo path: $PATH
echo workspace: $WORKSPACE
echo jenkins_home: $JENKINS_HOME
echo home: $HOME
echo pwd: `pwd`
echo REBUILD_VENV: $REBUILD_VENV
echo LANG: $LANG
env
git --version
svn --version
echo pip: `pip3 --version`
echo npm: `npm --version`

rm -rf ".allura-venv"

# ubuntu "python3-venv" isn't installed, so can't do the simple approach, instead use full "virtualenv" package
#  python3 -m venv .allura-venv || exit
pip3 install --user virtualenv || exit  # TODO: upgrade it?  seeing 15.x and 20.x
echo virtualenv 3: `python3 -m virtualenv --version`
# `python3 -m virtualenv` can sometimes default to using the py2 binary (weird!) so be explicit:
python3 -m virtualenv --python `which python3` .allura-venv || exit

. .allura-venv/bin/activate || exit

git clean -f -x  # remove test.log, nosetest.xml etc (don't use -d since it'd remove our venv dir)

echo venv-pip: `pip --version`
pip --version | grep 'python 3' || exit  # ensure on py3

# retry a few times
# MAIN_PIP="pip install -r requirements.txt --no-deps --upgrade --upgrade-strategy=only-if-needed"
MAIN_PIP="pip install -r requirements.txt --upgrade --upgrade-strategy=only-if-needed"
$MAIN_PIP || (echo "retrying pip install after short sleep"; sleep 2; $MAIN_PIP) || exit

pip install pycodestyle pyflakes coverage nose nose-xunitmp --no-deps --upgrade --upgrade-strategy=only-if-needed || exit

# handy script to download, compile, and install pysvn
curl https://raw.githubusercontent.com/reviewboard/pysvn-installer/master/install.py | python

# use "Allura* Forge* scripts" instead of "." so that .allura-venv doesn't get checked too (and '.' gives './' prefixed results which don't work out)
pyflakes Allura* Forge* scripts | awk -F\: '{printf "%s:%s: [E]%s\n", $1, $2, $3}' > pyflakes.txt
pycodestyle Allura* Forge* scripts > pep8.txt

./rebuild-all.bash

# fresh start with npm
#rm -rf node_modules
npm install || (echo "retrying npm install"; sleep 5; npm install) || (echo "retrying npm install"; sleep 5; npm install) || (echo "retrying npm install"; sleep 5; npm install) || (echo "retrying npm install"; sleep 5; npm install) || (echo "retrying npm install"; sleep 5; npm install) 

# TODO: ALLURA_VALIDATION=all
LANG=en_US.UTF-8 ./run_tests --with-xunitmp # --with-coverage --cover-erase
retcode=$?

#find . -name .coverage -maxdepth 2 | while read coveragefile; do pushd `dirname $coveragefile`; coverage xml --include='forge*,allura*'; popd; done;

rm -f call_count.csv
./scripts/perf/call_count.py --data-file call_count.csv


# debugging
echo npm: `npm --version`
echo hostname: `hostname --short`
echo NODE_NAME: $NODE_NAME

exit $retcode