#!/bin/sh
#
# This script calculates global codebase coverage, based on coverage
# of individual application packages.
#

DIRS="Allura Forge*"
EXCLUDES='*/migrations*,*/ez_setup/*,*allura/command/*'

for dir in $DIRS; do
    if [ ! -f $dir/.coverage ]; then
        echo "$dir/.coverage not found - please run ./run_test --with-coverage first"
    else
        ln -sf $dir/.coverage .coverage.$dir
    fi
done

coverage combine
coverage report --ignore-errors --include='Allura/*,Forge*' --omit=$EXCLUDES

if [ "$1" = "--html" ]; then
    coverage html --ignore-errors --include='Allura/*,Forge*' --omit=$EXCLUDES -d report.coverage
    coverage html --ignore-errors --include='Allura/*' --omit=$EXCLUDES -d Allura.coverage
fi
