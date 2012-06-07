import os.path
import shutil
from glob import glob
from subprocess import Popen, PIPE
import sys
import pkg_resources

toplevel_dir = os.path.abspath(os.path.dirname(__file__) + "/../..")

def run(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that nosetests can capture it
    (stdout, stderr) = proc.communicate()
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return proc.returncode

def run_with_output(cmd):
    proc = Popen(cmd, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that nosetests can capture it
    (stdout, stderr) = proc.communicate()
    sys.stderr.write(stderr)
    return proc.returncode, stdout, stderr

find_py = "find Allura Forge* -name '*.py'"

# a recepe from itertools doc
from itertools import izip_longest
def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)

def test_pyflakes():
    # skip some that aren't critical errors
    skips = [
        'imported but unused',
        'redefinition of unused',
        'assigned to but never used',
        '__version__',
    ]
    proc = Popen(find_py, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    (find_stdout, stderr) = proc.communicate()
    sys.stderr.write(stderr)
    assert proc.returncode == 0, proc.returncode

    # run pyflakes in batches, so it doesn't take tons of memory
    error = False
    all_files = [f for f in find_stdout.split('\n')
                 if '/migrations/' not in f and f.strip()]
    for files in grouper(20, all_files, fillvalue=''):
        cmd = "pyflakes " + ' '.join(files) + " | grep -v '" + "' | grep -v '".join(skips) + "'"
        #print 'Command was: %s' % cmd
        retval = run(cmd)
        if retval != 1:
            print
            #print 'Command was: %s' % cmd
            print 'Returned %s' % retval
            error = True

    if error:
        raise Exception('pyflakes failure, see stdout')

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
        'Allura/allura/lib/AsciiDammit.py',
        'ForgeMail/forgemail/sstress.py',
    ]
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + "' | xargs grep -v '^ *#' | grep 'print ' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")

def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1,123]:
        raise Exception('These should not use tab chars')

def code_check(cmd_app, sample_file_name, work_file_name):
    samples_dir = pkg_resources.resource_filename(
      'alluratest', 'data')
    if not os.path.exists(samples_dir):
        os.makedirs(samples_dir)

    pep8_sample_path = os.path.join(samples_dir, sample_file_name)
    pep8_work_path = os.path.join(samples_dir, work_file_name)

    initialize_mode = True
    if os.path.isfile(pep8_sample_path):
        initialize_mode = False

    if initialize_mode:
        fsample = open(pep8_sample_path, "w")
    else:
        fsample = open(pep8_sample_path, "r")
        sample_list = fsample.read().splitlines()
        fsample.close()
        fwork = open(pep8_work_path, "w")
        work_list = []

    proc = Popen(find_py, shell=True, cwd=toplevel_dir, stdout=PIPE, stderr=PIPE)
    (find_stdout, stderr) = proc.communicate()
    sys.stderr.write(stderr)
    assert proc.returncode == 0, proc.returncode

    all_files = [f for f in find_stdout.split('\n')
                 if '/migrations/' not in f and f.strip()]
    for files in grouper(20, all_files, fillvalue=''):
        cmd = cmd_app + " " + ' '.join(files)
        retval, stdout, stderr = run_with_output(cmd)

        if initialize_mode:
            fsample.write(stdout)
        else:
            fwork.write(stdout)
            work_list = work_list + stdout.splitlines()

    if initialize_mode:
        fsample.close()
    else:
        fwork.close()

        error = False
        for l in work_list:
            if l == '':
                 continue

            if l not in sample_list:
                sys.stdout.write("%s\n" % l)
                error = True
        if error:
            raise Exception('%s failure, see stdout' % cmd_app)
        else:
            shutil.copyfile(pep8_work_path, pep8_sample_path)

def test_pep8():
    code_check('pep8', 'pep8_sample.txt', 'pep8_work.txt')

def test_pyflakes():
    code_check('pyflakes', 'pyflakes_sample.txt', 'pyflakes_work.txt')
