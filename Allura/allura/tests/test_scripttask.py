import unittest
import mock

from allura.scripts.scripttask import ScriptTask


class TestScriptTask(unittest.TestCase):
    def setUp(self):
        class TestScriptTask(ScriptTask):
            _parser = mock.Mock()
            @classmethod
            def parser(cls):
                return cls._parser
        self.cls = TestScriptTask

    @mock.patch('allura.scripts.scripttask.sys')
    def test_arg_parsing(self, sys):
        "Make sure string of args gets correctly tokenized."
        parser = self.cls.parser()
        self.cls._execute_task('--dir "My Dir"')
        parser.parse_args.assert_called_once_with(['--dir', 'My Dir'])
        parser.reset_mock()
        self.cls._execute_task(None)
        parser.parse_args.assert_called_once_with([])
