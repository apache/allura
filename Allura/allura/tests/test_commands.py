from nose.tools import assert_raises

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script, set_neighborhood_features
from allura import model as M
from allura.lib.exceptions import InvalidNBFeatureValueError


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

def test_set_neighborhood_max_projects():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand('setnbfeatures')

    # a valid number
    cmd.run([test_config, str(n_id), 'max_projects', '50'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['max_projects'] == 50

    # none is also valid
    cmd.run([test_config, str(n_id), 'max_projects', 'None'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['max_projects'] == None

    # check validation
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'max_projects', 'string'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'max_projects', '2.8'])

def test_set_neighborhood_private():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand('setnbfeatures')

    # allow private projects
    cmd.run([test_config, str(n_id), 'private_projects', 'True'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['private_projects']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'private_projects', 'False'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert not neighborhood.features['private_projects']

    # check validation
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'private_projects', 'string'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'private_projects', '1'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'private_projects', '2.8'])

def test_set_neighborhood_google_analytics():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand('setnbfeatures')

    # allow private projects
    cmd.run([test_config, str(n_id), 'google_analytics', 'True'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['google_analytics']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'google_analytics', 'False'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert not neighborhood.features['google_analytics']

    # check validation
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'google_analytics', 'string'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'google_analytics', '1'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'google_analytics', '2.8'])

def test_set_neighborhood_css():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand('setnbfeatures')

    # none
    cmd.run([test_config, str(n_id), 'css', 'none'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'none'

    # picker
    cmd.run([test_config, str(n_id), 'css', 'picker'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'picker'

    # custom
    cmd.run([test_config, str(n_id), 'css', 'custom'])
    cmd.command()
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'custom'

    # check validation
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'string'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', '1'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', '2.8'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'None'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'True'])
