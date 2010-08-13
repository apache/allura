from distutils.sysconfig import get_python_lib

from nose.tools import assert_raises
from mock import patch

import build_virtualenv
from build_virtualenv import (VirtualenvRequirements,
                              error,
                              EnvCreator,
                              PySVNHack,
                              LocalPackages,
                              Inconsistencies,
                              PackageSmokeTest)


class TestVirtualenvRequirements:
    @patch('build_virtualenv.error')
    def test_that_it_doesnt_work_inside_an_activated_env(self, error):
        environ = dict(VIRTUAL_ENV='/some/path')
        VirtualenvRequirements(environ).enforce()
        error.assert_called_with(
            'refusing to build virtualenv while one is activated')

    @patch('build_virtualenv.error')
    @patch('build_virtualenv.exists')
    def test_that_it_doesnt_overwrite_existing_envs(self, exists, error):
        exists.return_value = True
        environ = dict()
        VirtualenvRequirements(environ).enforce()
        error.assert_called_with(
            'cowardly refusing to overwrite existing environment "env"')

    @patch('build_virtualenv.error')
    @patch('build_virtualenv.exists')
    def test_that_it_allows_env_creation_if_requirements_are_met(self,
                                                                 exists,
                                                                 error):
        exists.return_value = False
        environ = dict()
        VirtualenvRequirements(environ).enforce()
        assert not error.called


class TestEnvCreator:
    @patch('build_virtualenv.check_call')
    def test_that_it_creates_the_environment(self, check_call):
        EnvCreator().create()
        check_call.assert_called_with(
            'pip install --ignore-installed --environment=env --requirement=requirements.txt',
            shell=True)


class TestPySVNHack:
    @patch('build_virtualenv.symlink')
    @patch('build_virtualenv.get_python_lib')
    def test_that_it_writes_into_the_virtualenv_lib_dir(self,
                                                        get_python_lib,
                                                        symlink):
        fake_lib_dir = '/mylibdir/python2.6/site-packages'
        get_python_lib.return_value = fake_lib_dir
        PySVNHack().install()
        symlink.assert_called_with('/mylibdir/python2.6/site-packages/pysvn',
                                   'env/lib/python2.6/site-packages/pysvn')


class TestLocalPackages:
    @patch('build_virtualenv.check_call')
    def test_that_they_run_the_rebuild_script(self, check_call):
        LocalPackages().install()
        check_call.assert_called_with(
            '. env/bin/activate && bash rebuild.bash',
            shell=True)


class TestInconsistencies:
    @patch('sys.stdout')
    @patch('build_virtualenv.unchecked_call')
    def test_that_it_prints_explanation(self, unchecked_call, stdout):
        Inconsistencies().report()
        expected = 'Comparing installed packages to requirements:'
        assert expected in lines_printed_to_stdout(stdout)

    @patch('sys.stdout')
    @patch('build_virtualenv.unchecked_call')
    def test_that_it_compares_the_packages(self, unchecked_call, stdout):
        Inconsistencies().report()
        unchecked_call.assert_called_with(
            ". env/bin/activate && bash -c 'diff -u requirements.txt <(pip freeze -r requirements.txt)'",
            shell=True,
            stdout=stdout)


class TestPackageSmokeTest:
    @patch('sys.stdout')
    @patch('build_virtualenv.check_call')
    def test_that_it_tries_to_import_forge_packages(self,
                                                    check_call,
                                                    stdout):
        PackageSmokeTest().report()
        check_call.assert_called_with(". env/bin/activate && python -c 'import allura.model, allura.app, allura.controllers.root, forgediscussion.model, forgegit.model, forgehg.model, forgesvn.model, forgetracker.model, forgewiki.model'",
                                      shell=True)

    @patch('sys.stdout')
    @patch('build_virtualenv.check_call')
    def test_that_it_prints_status(self, check_call, stdout):
        PackageSmokeTest().report()
        lines_printed = lines_printed_to_stdout(stdout)
        assert 'Running import smoke test...' in lines_printed
        assert 'OK!' in lines_printed


class TestError:
    @patch('sys.stdout')
    @patch('sys.exit')
    def test_that_it_prints_error_message(self, exit, stdout):
        error('my message')
        assert 'error: my message' in lines_printed_to_stdout(stdout)

    @patch('sys.stdout')
    @patch('sys.exit')
    def test_that_it_exits(self, exit, stdout):
        error('my message')
        exit.assert_called_with(1)


def lines_printed_to_stdout(stdout):
    return [args[0] for args, kwargs in stdout.write.call_args_list]

