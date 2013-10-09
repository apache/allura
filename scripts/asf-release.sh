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

PREV_VERSION=`git tag -l asf_release_* | sort -rn | head -1 | sed -e 's/^asf_release_//'`
VERSION=`echo $PREV_VERSION | perl -pe '@_ = split /\./; $_[-1]++; $_ = join ".", @_'`
prompt VERSION "Version" "$VERSION"

RELEASE_BASE=allura-incubating-$VERSION
RELEASE_DIR=$RELEASE_DIR_BASE/$RELEASE_BASE
RELEASE_FILE=$RELEASE_DIR/$RELEASE_BASE.tar.gz
RELEASE_TAG=asf_release_$VERSION
CLOSE_DATE=`date -d '+72 hours' +%F`

scripts/changelog.py asf_release_$PREV_VERSION HEAD $VERSION > .changelog.tmp
echo >> .changelog.tmp
cat CHANGES >> .changelog.tmp
mv -f .changelog.tmp CHANGES
prompt DUMMY "Changelog updated; press enter when ready to commit" "enter"
git add CHANGES
git commit -m "CHANGES updated for ASF release $VERSION"

DEFAULT_KEY=`grep default-key ~/.gnupg/gpg.conf | sed -e 's/default-key //'`
if [[ -z "$DEFAULT_KEY" ]]; then
    DEFAULT_KEY=`gpg --list-secret-keys | head -3 | tail -1 | sed -e 's/^.*\///' | sed -e 's/ .*//'`
fi
prompt KEY "Key" "$DEFAULT_KEY"
FINGERPRINT=`gpg --fingerprint $KEY | grep fingerprint | cut -d' ' -f 17-20 | sed -e 's/ //g'`

prompt PLUS_VOTES "+1 votes"
prompt MINUS_VOTES "-1 votes" "0"
prompt ZERO_VOTES "+0 votes" "0"
prompt VOTE_THREAD_URL "URL for allura-dev VOTE thread"
prompt DISCUSS_THREAD_URL "URL for allura-dev DISCUSS thread"
prompt RAT_LOG_PASTEBIN_URL "URL for RAT log pastebin"

git tag $RELEASE_TAG
COMMIT_SHA=`git rev-parse $RELEASE_TAG`

mkdir -p $RELEASE_DIR
git archive -o $RELEASE_FILE --prefix $RELEASE_BASE/ $RELEASE_TAG

gpg --default-key $KEY --armor --output $RELEASE_FILE.asc --detach-sig $RELEASE_FILE
MD5_CHECKSUM=`md5sum $RELEASE_FILE` ; echo $MD5_CHECKSUM > $RELEASE_FILE.md5
SHA1_CHECKSUM=`shasum -a1 $RELEASE_FILE` ; echo $SHA1_CHECKSUM > $RELEASE_FILE.sha1
SHA512_CHECKSUM=`shasum -a512 $RELEASE_FILE` ; echo $SHA512_CHECKSUM > $RELEASE_FILE.sha512

echo "Release is ready at: $RELEASE_DIR"
echo "Once confirmed, push the CHANGES commit and release tag with:"
echo "    git push"
echo "    git push --tags"
echo "Then upload the files and signatures, and post the following:"
echo "-------------------------------------------------------------"
echo "Subject: [VOTE] Release of Apache Allura $VERSION (incubating)"
echo "-------------------------------------------------------------"
echo <<EOF
Hello,

This is a call for a vote on Apache Allura $VERSION incubating.

A vote was held on developer mailing list and it passed
with $PLUS_VOTES +1's, $MINUS_VOTES -1's, and $ZERO_VOTES +0's votes, and now requires a vote
on general@incubator.apache.org.

The [VOTE] and [DISCUSS] threads can be found at:
  [VOTE]:    $VOTE_THREAD_URL
  [DISCUSS]: $DISCUSS_THREAD_URL

Source tarball and signature are available at:
  https://dist.apache.org/repos/dist/dev/incubator/allura/$RELEASE_BASE.tar.gz
  https://dist.apache.org/repos/dist/dev/incubator/allura/$RELEASE_BASE.tar.gz.asc

Checksums:
  MD5:    $MD5_CHECKSUM
  SHA1:   $SHA1_CHECKSUM
  SHA512: $SHA512_CHECKSUM

The KEYS file can be found at:
  http://www.apache.org/dist/incubator/allura/KEYS

The release has been signed with key ($KEY):
  http://pgp.mit.edu:11371/pks/lookup?op=vindex&search=0x$FINGERPRINT

Source corresponding to this release can be found at:
  Commit: $COMMIT_SHA
  Tag:    asf_release_$VERSION
  Browse: https://git-wip-us.apache.org/repos/asf?p=incubator-allura.git;a=shortlog;h=refs/tags/asf_release_$VERSION

The RAT report is available at:
  $RAT_LOG_PASTEBIN_URL

Vote will be open for at least 72 hours ($CLOSE_DATE 12PM IST).

[ ] +1 approve
[ ] +0 no opinion
[ ] -1 disapprove (and reason why)

Thanks & Regards
EOF
echo "-------------------------------------------------------------"
