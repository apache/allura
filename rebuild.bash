for APP in Allura *Forge* NoWarnings pyforge
do
	echo "# installing $APP dependencies"
	pushd $APP
	python setup.py develop
	popd
done
