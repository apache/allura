#!/usr/bin/env bash

# This is so that git operations run as root, and can modify the scm repo files
#
# Up until git 2.11 and https://git.kernel.org/pub/scm/git/git.git/commit/?id=722ff7f876c8a2ad99c42434f58af098e61b96e8
# it was sufficient to `chmod u+s git-http-backend` so it ran as root, but that no longer works.
#
# A better fix would be to have files/dirs group owned by www-data but I tried that manually and didn't work
# maybe could put a "strace" within this command and hunt through all the files/dirs it writes to, to see what it
# writes to that www-data can't write to currently
# https://stackoverflow.com/a/46676868 or similar needed for strace to work thoguh

sudo --preserve-env /usr/lib/git-core/git-http-backend
