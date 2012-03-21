import mock
from nose.tools import assert_raises
from datadiff.tools import assert_equal
import pylons

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script, set_neighborhood_level, set_neighborhood_private
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

def test_set_neighborhood_level():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id

    cmd = set_neighborhood_level.SetNeighborhoodLevelCommand('setnblevel')
    cmd.run([test_config, str(n_id), 'gold'])
    cmd.command()

    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.level == 'gold'

def test_set_neighborhood_private():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id

    cmd = set_neighborhood_private.SetNeighborhoodPrivateCommand('setnbprivate')
    cmd.run([test_config, str(n_id), '1'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.allow_private

    cmd = set_neighborhood_private.SetNeighborhoodPrivateCommand('setnbprivate')
    cmd.run([test_config, str(n_id), '0'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert not neighborhood.allow_private
