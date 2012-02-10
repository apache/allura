# Allura Makefile
SHELL=/bin/bash

-include Makefile.def

# Constants
PID_PATH?=.

# Targets
test:
	ALLURA_VALIDATION=none ./run_tests

run:
	paster serve --reload development.ini
