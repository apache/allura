for APP in Allura* *Forge* NoWarnings
do
	echo "# setting up $APP dependencies"
	pushd $APP > /dev/null
	python setup.py -q develop || exit
	popd > /dev/null
done
