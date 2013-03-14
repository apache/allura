#!/bin/bash
for APP in Allura* *Forge* NoWarnings
do
    echo "# setting up $APP dependencies"
    pushd $APP > /dev/null
    python setup.py -q develop || echo "    # Error setting up $APP
    # You may want to run 'pip uninstall $APP' to un-register it so you don't get further errors."
    popd > /dev/null
done
