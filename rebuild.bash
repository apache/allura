for APP in Allura* *Forge* NoWarnings
do
	echo "# installing $APP dependencies"
	pushd $APP
	python setup.py develop || exit
	popd
done
