from nose.tools import assert_raises
from ming.orm import ThreadLocalORMSession
from mock import Mock

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script, set_neighborhood_features, \
                           create_neighborhood, show_models
from allura import model as M
from forgeblog import model as BM
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
    assert_raises(ValueError, cmd.run, [test_config, 'allura/tests/tscript_error.py' ])

def test_set_neighborhood_max_projects():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand('setnbfeatures')

    # a valid number
    cmd.run([test_config, str(n_id), 'max_projects', '50'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['max_projects'] == 50

    # none is also valid
    cmd.run([test_config, str(n_id), 'max_projects', 'None'])
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
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['private_projects']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'private_projects', 'False'])
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
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['google_analytics']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'google_analytics', 'False'])
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
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'none'

    # picker
    cmd.run([test_config, str(n_id), 'css', 'picker'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'picker'

    # custom
    cmd.run([test_config, str(n_id), 'css', 'custom'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['css'] == 'custom'

    # check validation
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'string'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', '1'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', '2.8'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'None'])
    assert_raises(InvalidNBFeatureValueError, cmd.run, [test_config, str(n_id), 'css', 'True'])

def test_update_neighborhood():
    cmd = create_neighborhood.UpdateNeighborhoodCommand('update-neighborhood')
    cmd.run([test_config, 'Projects', 'True'])
    ThreadLocalORMSession.close_all() # make sure the app_configs get freshly queried
    nb = M.Neighborhood.query.get(name='Projects')
    assert nb.has_home_tool == True

    cmd = create_neighborhood.UpdateNeighborhoodCommand('update-neighborhood')
    cmd.run([test_config, 'Projects', 'False'])
    ThreadLocalORMSession.close_all() # make sure the app_configs get freshly queried
    nb = M.Neighborhood.query.get(name='Projects')
    assert nb.has_home_tool == False


class TestEnsureIndexCommand(object):

    def test_run(self):
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd.run([test_config])

    def test_update_indexes_order(self):
        collection = Mock(name='collection')
        collection.index_information.return_value = {
                '_id_': {'key': '_id'},
                '_foo_bar': {'key': ['foo', 'bar']},
                }
        indexes = [
                Mock(unique=False, index_spec=('foo')),
                ]
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd._update_indexes(collection, indexes)

        collection_call_order = {}
        for i, call in enumerate(collection.mock_calls):
            method_name = call[0]
            collection_call_order[method_name] = i
        assert collection_call_order['ensure_index'] < collection_call_order['drop_index'], collection.mock_calls

