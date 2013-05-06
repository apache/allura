# Make single-file jslint script out of  main script (from jslint.com,
# patched by us to tweak its behavior, as it configurability leaves much
# to be desired) and Rhino support module. Needed because Rhino accepts
# only single file as script.

jslint.js: fulljslint.js rhino.js
	cat $^ >$@
