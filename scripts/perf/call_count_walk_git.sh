#!/bin/bash

if [[ $@ ]]
then
    revs=$@
else
    revs='HEAD -n 10'
    echo "No git revision range given, using $revs"
    echo "Other range formats like bdde98d..HEAD work too"
    echo
fi

current=`git rev-parse --abbrev-ref HEAD`
git rev-list --reverse $revs --oneline | while read commit
do
    echo $commit
    sha=${commit:0:7}
    git checkout -q $sha || { echo "Could not check out $sha, stopping.  You started on $current"; break; }
    ./call_count.py --id "$commit"
done
git checkout -q $current