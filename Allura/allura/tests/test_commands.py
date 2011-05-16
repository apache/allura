import mock
from nose.tools import assert_raises
from datadiff.tools import assert_equal
import pylons

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script
from allura import model as M


test_config = 'test.ini#main'

class EmptyClass(object): pass

def setUp(self):
    """Method called by nose before running each test"""
    #setup_basic_test(app_name='main_with_amqp')
    setup_basic_test()
    setup_global_objects()

def test_script():
    cmd = script.ScriptCommand('script')
    cmd.run([test_config, 'allura/tests/tscript.py' ])
    cmd.command()
    assert_raises(ValueError, cmd.run, [test_config, 'allura/tests/tscript_error.py' ])
