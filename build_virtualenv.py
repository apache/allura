from os.path import exists
import sys
import os
from os import symlink
from os.path import join
from distutils.sysconfig import get_python_lib
from subprocess import check_call
from subprocess import call as unchecked_call


ENV_DIR = 'env'
REQUIREMENTS_FILE = 'requirements.txt'


# If the PYTHONDONTWRITEBYTECODE variable is set, it confuses easy_install
# into installing pip as a zipped egg, which breaks pip as of 0.7.1. A fix
# should be in the next release.
if 'PYTHONDONTWRITEBYTECODE' in os.environ:
    del os.environ['PYTHONDONTWRITEBYTECODE']


def main():
    VirtualenvRequirements(os.environ).enforce()
    EnvCreator().create()
    PySVNHack().install()
    LocalPackages().install()
    Inconsistencies().report()
    PackageSmokeTest().report()


class VirtualenvRequirements:
    def __init__(self, environ):
        self.environ = environ

    def enforce(self):
        if self.virtualenv_is_activated():
            error('refusing to build virtualenv while one is activated')
        elif self.virtualenv_exists():
            error('cowardly refusing to overwrite existing environment "%s"'
                  % ENV_DIR)

    def virtualenv_is_activated(self):
        return 'VIRTUAL_ENV' in self.environ

    def virtualenv_exists(self):
        return exists(ENV_DIR)


class EnvCreator:
    def create(self):
        arguments = ['--ignore-installed',
                     '--environment=%s' % ENV_DIR,
                     '--requirement=%s' % REQUIREMENTS_FILE]
        command = 'pip install %s' % ' '.join(arguments)
        check_call(command, shell=True)


class PySVNHack:
    def install(self):
        real_pysvn_path = join(get_python_lib(), 'pysvn')
        major, minor = sys.version_info[:2]
        python_version = '%i.%i' % (major, minor)
        pysvn_symlink_path = ('%s/lib/python%s/site-packages/pysvn' %
                              (ENV_DIR, python_version))
        symlink(real_pysvn_path, pysvn_symlink_path)


class LocalPackages:
    def install(self):
        check_call('. env/bin/activate && bash rebuild.bash', shell=True)


class Inconsistencies:
    def report(self):
        print
        print 'Comparing installed packages to requirements:'
        print
        bash_command = (
            'diff -u %s <(pip freeze -r %s)' % (REQUIREMENTS_FILE,
                                                REQUIREMENTS_FILE))
        unchecked_call(
            ". %s/bin/activate && bash -c '%s'" % (ENV_DIR, bash_command),
            shell=True,
            stdout=sys.stdout)


class PackageSmokeTest:
    def report(self):
        print
        print 'Running import smoke test...'
        packages_to_import = ['allura.model',
                              'allura.app',
                              'allura.controllers.root',
                              'forgediscussion.model',
                              'forgegit.model',
                              'forgehg.model',
                              'forgesvn.model',
                              'forgetracker.model',
                              'forgewiki.model']
        packages = ', '.join(packages_to_import)
        check_call(". %s/bin/activate && python -c 'import %s'" %
                   (ENV_DIR, packages),
                   shell=True)
        print 'OK!'


def error(message):
    print 'error: %s' % message
    sys.exit(1)


if __name__ == '__main__':
    main()

