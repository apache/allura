import os.path
from glob import glob
from subprocess import Popen, PIPE
import sys

toplevel_dir = os.path.abspath(os.path.dirname(__file__) + "/../..")

def run(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that nosetests can capture it
    (stdout, stderr) = proc.communicate()
    print stdout,
    print >>sys.stderr, stderr,
    return proc.returncode

find_py = "find Allura Forge* -name '*.py'"

def test_pyflakes():
    # skip some that aren't critical errors
    skips = [
        'imported but unused',
        'redefinition of unused',
        'assigned to but never used',
    ]
    cmd = find_py + " | grep -v '/migrations/' | xargs pyflakes"
    print 'Not skipping anything via grep:'
    print cmd
    print
    run(cmd)

    print
    print 'Skipping some stuff via grep:'
    cmd += " | grep -v '" + "' | grep -v '".join(skips) + "'"
    print cmd
    print

    retval = run(cmd)
    if retval != 1:
        raise Exception('pyflakes failure, returned %s' % retval)

def test_no_now():
    if run(find_py + " | xargs grep '\.now(' ") not in [1,123]:
        raise Exception("These should use .utcnow()")
    if run(find_py + " | xargs grep '\.fromtimestamp(' ") not in [1,123]:
        raise Exception("These should use .utcfromtimestamp()")

def test_no_prints():
    skips = [
        '/tests/',
        'Allura/allura/command/',
        'Allura/ldap-setup.py',
        'Allura/ldap-userconfig.py',
        'Allura/ez_setup/',
        'Allura/push_re.py',
        'ForgeMail/forgemail/sstress.py',
    ]
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + "' | xargs grep -v '^ *#' | grep 'print ' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")

def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1,123]:
        raise Exception('These should not use tab chars')
