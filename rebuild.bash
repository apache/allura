echo '# setup pyforge...'
pushd pyforge
python setup.py develop
popd
echo '# setup ForgeDiscussion...'
pushd ForgeDiscussion
python setup.py develop
popd
echo '# setup ForgeGit...'
pushd ForgeGit
python setup.py develop
popd
echo '# setup ForgeHg...'
pushd ForgeHg
python setup.py develop
popd
echo '# setup ForgeLink...'
pushd ForgeLink
python setup.py develop
popd
echo '# setup ForgeSVN...'
pushd ForgeSVN
python setup.py develop
popd
echo '# setup ForgeMail...'
pushd ForgeMail
python setup.py develop
popd
echo '# setup ForgeTracker...'
pushd ForgeTracker
python setup.py develop
popd
echo '# setup ForgeWiki...'
pushd ForgeWiki
python setup.py develop
popd
