from nose.tools import assert_raises
from datadiff.tools import assert_equal
from ming.orm import ThreadLocalORMSession
from mock import Mock, call

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script, set_neighborhood_features, \
                           create_neighborhood, show_models, taskd_cleanup
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
                '_foo_bar': {'key': [('foo', 1), ('bar', 1)]},
                }
        indexes = [
                Mock(unique=False, index_spec=[('foo', 1)]),
                ]
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd._update_indexes(collection, indexes)

        collection_call_order = {}
        for i, call in enumerate(collection.mock_calls):
            method_name = call[0]
            collection_call_order[method_name] = i
        assert collection_call_order['ensure_index'] < collection_call_order['drop_index'], collection.mock_calls

    def test_update_indexes_unique_changes(self):
        collection = Mock(name='collection')
        # expecting these ensure_index calls, we'll make their return values normal
        # for easier assertions later
        collection.ensure_index.side_effect = ['_foo_bar_temporary_extra_field_for_indexing',
                                               '_foo_bar',
                                               '_foo_baz_temporary_extra_field_for_indexing',
                                               '_foo_baz',
                                               '_foo_baz',
                                               '_foo_bar',
                                               ]
        collection.index_information.return_value = {
                '_id_': {'key': '_id'},
                '_foo_bar': {'key': [('foo', 1), ('bar', 1)], 'unique': True},
                '_foo_baz': {'key': [('foo', 1), ('baz', 1)]},
                }
        indexes = [
                Mock(index_spec=[('foo', 1), ('bar', 1)], unique=False, ),
                Mock(index_spec=[('foo', 1), ('baz', 1)], unique=True, ),
                ]

        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd._update_indexes(collection, indexes)

        assert_equal(collection.mock_calls, [
            call.index_information(),
            call.ensure_index([('foo', 1), ('bar', 1), ('temporary_extra_field_for_indexing', 1)]),
            call.drop_index('_foo_bar'),
            call.ensure_index([('foo', 1), ('bar', 1)], unique=False),
            call.drop_index('_foo_bar_temporary_extra_field_for_indexing'),
            call.ensure_index([('foo', 1), ('baz', 1), ('temporary_extra_field_for_indexing', 1)]),
            call.drop_index('_foo_baz'),
            call.ensure_index([('foo', 1), ('baz', 1)], unique=True),
            call.drop_index('_foo_baz_temporary_extra_field_for_indexing'),
            call.ensure_index([('foo', 1), ('baz', 1)], unique=True),
            call.ensure_index([('foo', 1), ('bar', 1)], background=True)
        ])


class TestTaskdCleanupCommand(object):

    def setUp(self):
        self.cmd_class = taskd_cleanup.TaskdCleanupCommand
        self.cmd_class._check_taskd_status = lambda x, p: 'OK'
        self.cmd_class._check_task = lambda x, p, t: 'OK'
        self.cmd_class._busy_tasks = lambda x: []
        self.cmd_class._taskd_pids = lambda x: ['1111']
        self.cmd_class._kill_stuck_taskd = Mock()
        self.cmd_class._complete_suspicious_tasks = lambda x: []

    def test_forsaken_tasks(self):
        # forsaken task
        task = Mock(state='busy', process='host pid 1111', result='')
        self.cmd_class._busy_tasks = lambda x: [task]
        self.cmd_class._taskd_pids = lambda x: ['2222']

        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert task.state == 'error', task.state
        assert task.result == 'Can\'t find taskd with given pid', task.result
        assert cmd.error_tasks == [task]

        # task actually running taskd pid == task.process pid == 2222
        task = Mock(state='busy', process='host pid 2222', result='')
        self.cmd_class._busy_tasks = lambda x: [task]
        self.cmd_class._taskd_pids = lambda x: ['2222']

        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        # nothing should change
        assert task.state == 'busy', task.state
        assert task.result == '', task.result
        assert cmd.error_tasks == []

    def test_stuck_taskd(self):
        # does not stuck
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert cmd.stuck_pids == [], cmd.stuck_pids

        # stuck
        self.cmd_class._check_taskd_status = lambda x, p: 'STUCK'
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert cmd.stuck_pids == ['1111'], cmd.stuck_pids

        # stuck with -k option
        self.cmd_class._check_taskd_status = lambda x, p: 'STUCK'
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, '-k', 'fake.log'])
        cmd._kill_stuck_taskd.assert_called_with('1111')
        assert cmd.stuck_pids == ['1111'], cmd.stuck_pids

    def test_suspicious_tasks(self):
        # task1 is lost
        task1 = Mock(state='busy', process='host pid 1111', result='', _id=1)
        task2 = Mock(state='busy', process='host pid 1111', result='', _id=2)
        self.cmd_class._busy_tasks = lambda x: [task1, task2]
        self.cmd_class._check_task = lambda x, p, t: 'FAIL' if t._id == 1 else 'OK'
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert cmd.suspicious_tasks == [task1], cmd.suspicious_tasks
        assert cmd.error_tasks == [task1], cmd.error_tasks
        assert task1.state == 'error'
        assert task1.result == 'Forsaken task'

        # task1 seems lost, but it just moved quickly
        task1 = Mock(state='complete', process='host pid 1111', result='', _id=1)
        task2 = Mock(state='busy', process='host pid 1111', result='', _id=2)
        self.cmd_class._complete_suspicious_tasks = lambda x: [1]
        self.cmd_class._busy_tasks = lambda x: [task1, task2]
        self.cmd_class._check_task = lambda x, p, t: 'FAIL' if t._id == 1 else 'OK'
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert cmd.suspicious_tasks == [task1], cmd.suspicious_tasks
        assert cmd.error_tasks == [], cmd.error_tasks
        assert task1.state == 'complete'
