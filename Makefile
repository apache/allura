# Allura Makefile
SHELL=/bin/bash

-include Makefile.def

# Constants
PID_PATH?=.

# Targets
test:
ifdef BB
# running on buildbot (Makefile.def.buildbot sets BB to 1)
# setup pysvn
	-[ ! -f $(VIRTUAL_ENV)/lib/python2.7/site-packages/pysvn ] && ln -s /usr/lib64/python2.7/site-packages/pysvn $(VIRTUAL_ENV)/lib/python2.7/site-packages/
	-[ ! -d $(VIRTUAL_ENV)/lib/python2.7/site-packages/pysvn-1.7.5-py2.7.egg-info ] && mkdir $(VIRTUAL_ENV)/lib/python2.7/site-packages/pysvn-1.7.5-py2.7.egg-info
# rebuild apps
	./rebuild-all.bash
endif
	ALLURA_VALIDATION=none ./run_tests
	./run_clonedigger

run:
	paster serve --reload Allura/development.ini
