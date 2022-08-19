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

set -e -o pipefail

echo "This will prep a release, it'll make a local commit and tag but not push them.  You should have PGP keys set up and ready"

function prompt() {
    ivar="$1"
    prompt_str="$2: "
    default="$3"
    if [[ -n "$default" ]]; then
        prompt_str="$prompt_str[$default] "
    fi
    echo -n "$prompt_str"
    read $ivar
    eval $ivar=\${$ivar:-$default}
}

RELEASE_DIR_BASE=/tmp

PREV_VERSION=`git tag -l rel/* | sort -rV | head -1 | sed -e 's/^rel\///'`
VERSION=`echo $PREV_VERSION | perl -pe '@_ = split /\./; $_[-1]++; $_ = join ".", @_'`
prompt VERSION "Version" "$VERSION"

RELEASE_BASE=allura-$VERSION
RELEASE_DIR=$RELEASE_DIR_BASE/$RELEASE_BASE
RELEASE_FILENAME=$RELEASE_BASE.tar.gz
RELEASE_FILE_EXTRACTED=$RELEASE_DIR/$RELEASE_BASE
RELEASE_FILE=$RELEASE_DIR/$RELEASE_FILENAME
RELEASE_TAG=rel/$VERSION
CLOSE_DATE=`date -d '+72 hours' -R --utc | sed -e 's/+0000/UTC/'`
YEAR=`date +%Y`

sed -i -e "s/2012-[0-9]\{4\} /2012-$YEAR /" NOTICE */NOTICE */docs/conf.py
git commit -m "Update copyright year" NOTICE */NOTICE */docs/conf.py || echo "no copyright year changes to commit"

scripts/changelog.py rel/$PREV_VERSION HEAD $VERSION > .changelog.tmp
echo >> .changelog.tmp
cat CHANGES >> .changelog.tmp
mv -f .changelog.tmp CHANGES
prompt DUMMY "CHANGES file populated, please edit it to summarize, write upgrade notes etc.  Press enter when ready to commit" "enter"
git commit -m "CHANGES updated for ASF release $VERSION" CHANGES

DEFAULT_KEY=`grep ^default-key ~/.gnupg/gpg.conf | sed -e 's/default-key //'` || true  # ok if doesn't exit ok
if [[ -z "$DEFAULT_KEY" ]]; then
    DEFAULT_KEY=`gpg --list-secret-keys | egrep '[0-9A-F]{8}' | head -1 | sed -e 's/\W//g'`
fi
prompt KEY "PGP Key to sign with" "$DEFAULT_KEY"

prompt RAT_LOG_PASTEBIN_URL "URL for RAT log pastebin (see scripts/src-license-check to create RAT report)"

git tag $RELEASE_TAG
COMMIT_SHA=`git rev-parse $RELEASE_TAG`

mkdir -p $RELEASE_DIR
git archive -o $RELEASE_FILE --prefix $RELEASE_BASE/ $RELEASE_TAG

# expand archive, run broccoli & sass in it, rebuild archive
cd $RELEASE_DIR
tar xzf $RELEASE_FILE
cd $RELEASE_FILE_EXTRACTED
npm ci >/dev/null
NODE_ENV=production npm run build
#NODE_ENV=production npm run css
rm -rf node_modules
cd ..
tar czf $RELEASE_FILE $RELEASE_BASE
rm -rf $RELEASE_FILE_EXTRACTED

gpg --default-key $KEY --armor --output $RELEASE_FILE.asc --detach-sig $RELEASE_FILE
SHA512_CHECKSUM=`cd $RELEASE_DIR ; shasum -a512 $RELEASE_FILENAME` ; echo "$SHA512_CHECKSUM" > $RELEASE_FILE.sha512

echo
echo
echo
echo "Release is ready at: $RELEASE_DIR"
echo "Once confirmed, push the CHANGES commit with:"
echo "    git push"
echo "Then upload the files and signatures to https://dist.apache.org/repos/dist/dev/allura/ (SVN repo)"
echo "And post the following:"
echo "-------------------------------------------------------------"
echo "Subject: [VOTE] Release of Apache Allura $VERSION"
echo "-------------------------------------------------------------"
cat <<EOF
Hello,

This is a call for a vote on Apache Allura $VERSION.

Source tarball, signature and checksums are available at:
  https://dist.apache.org/repos/dist/dev/allura/

Checksums:
  SHA512: $SHA512_CHECKSUM

The KEYS file can be found at:
  https://www.apache.org/dist/allura/KEYS

The release has been signed with key $KEY:
  http://pgp.mit.edu:11371/pks/lookup?op=vindex&search=0x$KEY

Source corresponding to this release can be found at:
  Commit: $COMMIT_SHA
  Tag:    $RELEASE_TAG (pending successful vote)
  Browse: https://forge-allura.apache.org/p/allura/git/ci/$COMMIT_SHA/log/

Changes for this version are listed at:
  https://forge-allura.apache.org/p/allura/git/ci/$COMMIT_SHA/tree/CHANGES

The RAT license report is available at:
  $RAT_LOG_PASTEBIN_URL

Vote will be open for at least 72 hours ($CLOSE_DATE).  Votes from Allura PMC members are binding, but we welcome all community members to vote as well.

[ ] +1 approve
[ ] +0 no opinion
[ ] -1 disapprove (and reason why)

Thanks & Regards
EOF
echo "-------------------------------------------------------------"
echo "After a successful vote (just in case you have to redo the release), you can push the tag:"
echo "    git push origin $RELEASE_TAG"
