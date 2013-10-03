#!/bin/bash

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



mkdir $RELEASE_DIR
ln -s . $RELEASE_BASE
tar -czf $RELEASE_FILE \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude="$RELEASE_BASE/*/LICENSE" \
    --exclude="$RELEASE_BASE/*/NOTICE" \
    --exclude="$RELEASE_BASE/allura-incubating-*" \
    $RELEASE_BASE/*
rm -f $RELEASE_BASE

gpg --default-key $KEY --armor --output $RELEASE_FILE.asc --detach-sig $RELEASE_FILE
MD5_CHECKSUM=`md5sum $RELEASE_FILE` ; echo $MD5_CHECKSUM > $RELEASE_FILE.md5
SHA1_CHECKSUM=`shasum -a1 $RELEASE_FILE` ; echo $SHA1_CHECKSUM > $RELEASE_FILE.sha1
SHA512_CHECKSUM=`shasum -a512 $RELEASE_FILE` ; echo $SHA512_CHECKSUM > $RELEASE_FILE.sha512

git tag asf_release_$VERSION
#git push origin asf_release_$VERSION
COMMIT_SHA=`git rev-parse asf_release_$VERSION`

CLOSE_DATE=`date -d '+72 hours' +%F`

echo "Release is ready at: $RELEASE_DIR"
echo "Once confirmed, push release tag with: git push origin asf_release_$VERSION"
echo "Then upload the files and signatures, and post the following:"
echo "-------------------------------------------------------------"
echo "Subject: [VOTE] Release of Apache Allura $VERSION (incubating)"
echo "-------------------------------------------------------------"
echo <<EOF
Hello,

This is a call for a vote on Apache Allura 1.0.0 incubating.

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
