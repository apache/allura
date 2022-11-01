#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


import datetime

from testfixtures import OutputCapture

from ming.base import Object
from ming.orm import ThreadLocalORMSession
from mock import Mock, call, patch
import pytest
import pymongo
import pkg_resources

from alluratest.controller import setup_basic_test, setup_global_objects, setup_unit_test
from allura.command import base, script, set_neighborhood_features, \
    create_neighborhood, show_models, taskd_cleanup, taskd
from allura import model as M
from allura.lib.exceptions import InvalidNBFeatureValueError
from allura.tests import decorators as td


test_config = pkg_resources.resource_filename(
    'allura', '../test.ini') + '#main'


class EmptyClass:
    pass


def setup_module():
    setup_basic_test()
    setup_global_objects()
    setup_unit_test()


def test_script():
    cmd = script.ScriptCommand('script')
    cmd.run(
        [test_config, pkg_resources.resource_filename('allura', 'tests/tscript.py')])
    pytest.raises(ValueError, cmd.run,
                  [test_config, pkg_resources.resource_filename('allura', 'tests/tscript_error.py')])


def test_set_neighborhood_max_projects():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand(
        'setnbfeatures')

    # a valid number
    cmd.run([test_config, str(n_id), 'max_projects', '50'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['max_projects'] == 50

    # none is also valid
    cmd.run([test_config, str(n_id), 'max_projects', 'None'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['max_projects'] is None

    # check validation
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'max_projects', 'string'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'max_projects', '2.8'])


def test_set_neighborhood_private():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand(
        'setnbfeatures')

    # allow private projects
    cmd.run([test_config, str(n_id), 'private_projects', 'True'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['private_projects']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'private_projects', 'False'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert not neighborhood.features['private_projects']

    # check validation
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'private_projects', 'string'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'private_projects', '1'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'private_projects', '2.8'])


def test_set_neighborhood_google_analytics():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand(
        'setnbfeatures')

    # allow private projects
    cmd.run([test_config, str(n_id), 'google_analytics', 'True'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert neighborhood.features['google_analytics']

    # disallow private projects
    cmd.run([test_config, str(n_id), 'google_analytics', 'False'])
    neighborhood = M.Neighborhood.query.get(_id=n_id)
    assert not neighborhood.features['google_analytics']

    # check validation
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'google_analytics', 'string'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'google_analytics', '1'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'google_analytics', '2.8'])


def test_set_neighborhood_css():
    neighborhood = M.Neighborhood.query.find().first()
    n_id = neighborhood._id
    cmd = set_neighborhood_features.SetNeighborhoodFeaturesCommand(
        'setnbfeatures')

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
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'css', 'string'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'css', '1'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'css', '2.8'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'css', 'None'])
    pytest.raises(InvalidNBFeatureValueError, cmd.run,
                  [test_config, str(n_id), 'css', 'True'])


def test_update_neighborhood():
    cmd = create_neighborhood.UpdateNeighborhoodCommand('update-neighborhood')
    cmd.run([test_config, 'Projects', 'True'])
    # make sure the app_configs get freshly queried
    ThreadLocalORMSession.close_all()
    nb = M.Neighborhood.query.get(name='Projects')
    assert nb.has_home_tool is True

    cmd = create_neighborhood.UpdateNeighborhoodCommand('update-neighborhood')
    cmd.run([test_config, 'Projects', 'False'])
    # make sure the app_configs get freshly queried
    ThreadLocalORMSession.close_all()
    nb = M.Neighborhood.query.get(name='Projects')
    assert nb.has_home_tool is False


class TestEnsureIndexCommand:

    def test_run(self):
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd.run([test_config])

    def test_no_drop(self):
        collection = Mock(name='collection')
        collection.index_information.return_value = {
            '_id_': {'key': '_id'},
            '_foo_bar': {'key': [('foo', 1), ('bar', 1)]},
        }
        indexes = [
            Mock(unique=False, index_spec=[('foo', 1)],
                 index_options={'unique': False, 'sparse': False}),
        ]
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd.options = Object(clean=False)
        cmd._update_indexes(collection, indexes)
        assert collection.ensure_index.called
        assert not collection.drop_index.called

    def test_update_indexes_order(self):
        collection = Mock(name='collection')
        collection.index_information.return_value = {
            '_id_': {'key': '_id'},
            '_foo_bar': {'key': [('foo', 1), ('bar', 1)]},
        }
        indexes = [
            Mock(unique=False, index_spec=[('foo', 1)],
                 index_options={'unique': False, 'sparse': False}),
        ]
        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd.options = Object(clean=True)
        cmd._update_indexes(collection, indexes)

        collection_call_order = {}
        for i, call_ in enumerate(collection.mock_calls):
            method_name = call_[0]
            collection_call_order[method_name] = i
        assert collection_call_order['ensure_index'] < collection_call_order['drop_index'], collection.mock_calls

    def test_update_indexes_unique_changes(self):
        collection = Mock(name='collection')
        # expecting these ensure_index calls, we'll make their return values normal
        # for easier assertions later
        collection.ensure_index.side_effect = [
            '_foo_bar_temporary_extra_field_for_indexing',
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
            Mock(index_spec=[('foo', 1), ('bar', 1)], unique=False,
                 index_options={'unique': False, 'sparse': False}),
            Mock(index_spec=[('foo', 1), ('baz', 1)], unique=True,
                 index_options={'unique': True, 'sparse': False}),
        ]

        cmd = show_models.EnsureIndexCommand('ensure_index')
        cmd._update_indexes(collection, indexes)

        assert collection.mock_calls == [
            call.index_information(),
            call.ensure_index(
                [('foo', 1), ('bar', 1), ('temporary_extra_field_for_indexing', 1)]),
            call.drop_index('_foo_bar'),
            call.ensure_index([('foo', 1), ('bar', 1)], unique=False),
            call.drop_index('_foo_bar_temporary_extra_field_for_indexing'),
            call.ensure_index(
                [('foo', 1), ('baz', 1), ('temporary_extra_field_for_indexing', 1)]),
            call.drop_index('_foo_baz'),
            call.ensure_index([('foo', 1), ('baz', 1)], unique=True),
            call.drop_index('_foo_baz_temporary_extra_field_for_indexing'),
            call.ensure_index([('foo', 1), ('baz', 1)], unique=True, sparse=False),
            call.ensure_index([('foo', 1), ('bar', 1)], unique=False, sparse=False, background=True)
        ]


class TestTaskCommand:

    def teardown_method(self, method):
        M.MonQTask.query.remove({})

    def test_commit(self):
        exit_code = taskd.TaskCommand('task').run([test_config, 'commit'])
        assert M.MonQTask.query.find({'task_name': 'allura.tasks.index_tasks.commit'}).count() == 1
        assert exit_code == 0

    def test_list(self):
        exit_code = taskd.TaskCommand('task').run([test_config, 'list'])
        assert exit_code == 0

    def test_count(self):
        exit_code = taskd.TaskCommand('task').run([test_config, 'count'])
        assert exit_code == 0

    def test_retry(self):
        # self.test_commit()
        exit_code = taskd.TaskCommand('task').run([
            test_config, 'retry',
            '--filter-name-prefix', 'allura.tasks.index_tasks.',
            '--filter-result-regex', 'pysolr',
        ])
        assert exit_code == 0

    def test_purge(self):
        # create task
        self.test_commit()
        assert M.MonQTask.query.find().count() == 1
        M.MonQTask.query.update({'task_name': 'allura.tasks.index_tasks.commit'}, {'$set': {'state': 'complete'}})
        # run purge; verify 0 records
        exit_code = taskd.TaskCommand('task').run([
            test_config, 'purge',
        ])
        assert exit_code == 0
        assert M.MonQTask.query.find().count() == 0

    def test_purge_old_only(self):
        # create task
        self.test_commit()
        assert M.MonQTask.query.find().count() == 1

        # force task to be in complete state
        M.MonQTask.query.update({'task_name': 'allura.tasks.index_tasks.commit'}, {'$set': {'state': 'complete'}})
        # run purge; verify no records deleted
        exit_code = taskd.TaskCommand('task').run([
            test_config, 'purge', '--filter-queued-days-ago', '180',
        ])
        assert exit_code == 0
        assert M.MonQTask.query.find().count() == 1

        # modify task to be old
        then = datetime.datetime.utcnow() - datetime.timedelta(days=200)
        M.MonQTask.query.update({'task_name': 'allura.tasks.index_tasks.commit'},
                                {'$set': {'time_queue': then, 'time_start': then, 'time_stop': then}})

        # run purge; verify old tasks deleted
        exit_code = taskd.TaskCommand('task').run([
            test_config, 'purge', '--filter-queued-days-ago', '180',
        ])
        assert exit_code == 0
        assert M.MonQTask.query.find().count() == 0


class TestTaskdCleanupCommand:

    def setup_method(self, method):
        self.cmd_class = taskd_cleanup.TaskdCleanupCommand
        self.old_check_taskd_status = self.cmd_class._check_taskd_status
        self.cmd_class._check_taskd_status = lambda x, p: 'OK'
        self.old_check_task = self.cmd_class._check_task
        self.cmd_class._check_task = lambda x, p, t: 'OK'
        self.old_busy_tasks = self.cmd_class._busy_tasks
        self.cmd_class._busy_tasks = lambda x: []
        self.old_taskd_pids = self.cmd_class._taskd_pids
        self.cmd_class._taskd_pids = lambda x: ['1111']
        self.old_kill_stuck_taskd = self.cmd_class._kill_stuck_taskd
        self.cmd_class._kill_stuck_taskd = Mock()
        self.old_complete_suspicious_tasks = self.cmd_class._complete_suspicious_tasks
        self.cmd_class._complete_suspicious_tasks = lambda x: []

    def teardown_method(self, method):
        # need to clean up setup_method mocking for unit tests below to work properly
        self.cmd_class._check_taskd_status = self.old_check_taskd_status
        self.cmd_class._check_task = self.old_check_task
        self.cmd_class._busy_tasks = self.old_busy_tasks
        self.cmd_class._taskd_pids = self.old_taskd_pids
        self.cmd_class._kill_stuck_taskd = self.old_kill_stuck_taskd
        self.cmd_class._complete_suspicious_tasks = self.old_complete_suspicious_tasks

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
        task1 = Mock(state='complete',
                     process='host pid 1111', result='', _id=1)
        task2 = Mock(state='busy', process='host pid 1111', result='', _id=2)
        self.cmd_class._complete_suspicious_tasks = lambda x: [1]
        self.cmd_class._busy_tasks = lambda x: [task1, task2]
        self.cmd_class._check_task = lambda x, p, t: 'FAIL' if t._id == 1 else 'OK'
        cmd = self.cmd_class('taskd_command')
        cmd.run([test_config, 'fake.log'])
        assert cmd.suspicious_tasks == [task1], cmd.suspicious_tasks
        assert cmd.error_tasks == [], cmd.error_tasks
        assert task1.state == 'complete'


# taskd_cleanup unit tests
def test_status_log_retries():
    cmd = taskd_cleanup.TaskdCleanupCommand('taskd_command')
    cmd._taskd_status = Mock()
    cmd._taskd_status.return_value = ''
    cmd.options = Mock(num_retry=10)
    cmd._check_taskd_status(123)
    expected_calls = [call(123, False if i == 0 else True) for i in range(10)]
    assert cmd._taskd_status.mock_calls == expected_calls

    cmd._taskd_status = Mock()
    cmd._taskd_status.return_value = ''
    cmd.options = Mock(num_retry=3)
    cmd._check_task(123, Mock())
    expected_calls = [call(123, False if i == 0 else True) for i in range(3)]
    assert cmd._taskd_status.mock_calls == expected_calls


class TestShowModels:

    def test_show_models(self):
        cmd = show_models.ShowModelsCommand('models')
        with OutputCapture() as output:
            cmd.run([test_config])
        assert '''allura.model.notification.SiteNotification
         - <FieldProperty _id>
         - <FieldProperty content>
        ''' in output.captured

class TestReindexAsTask:

    cmd = 'allura.command.show_models.ReindexCommand'
    task_name = 'allura.command.base.run_command'

    def test_command_post(self):
        show_models.ReindexCommand.post('-p "project 3"')
        tasks = M.MonQTask.query.find({'task_name': self.task_name}).all()
        assert len(tasks) == 1
        task = tasks[0]
        assert task.args == [self.cmd, '-p "project 3"']

    def test_command_doc(self):
        assert 'Usage:' in show_models.ReindexCommand.__doc__

    @patch('allura.command.show_models.ReindexCommand')
    def test_run_command(self, command):
        command.__name__ = 'ReindexCommand'
        base.run_command(self.cmd, 'dev.ini -p "project 3"')
        command(command.__name__).run.assert_called_with(
            ['dev.ini', '-p', 'project 3'])

    def test_invalid_args(self):
        M.MonQTask.query.remove()
        show_models.ReindexCommand.post('--invalid-option')
        try:
            with td.raises(Exception) as e:
                M.MonQTask.run_ready()
            assert 'Error parsing args' in str(e.exc)
        finally:
            # cleanup - remove bad MonQTask
            M.MonQTask.query.remove()


class TestReindexCommand:

    @patch('allura.command.show_models.g')
    def test_skip_solr_delete(self, g):
        cmd = show_models.ReindexCommand('reindex')
        cmd.run([test_config, '-p', 'test', '--solr'])
        assert g.solr.delete.called, 'solr.delete() must be called'
        g.solr.delete.reset_mock()
        cmd.run([test_config, '-p', 'test', '--solr', '--skip-solr-delete'])
        assert not g.solr.delete.called, 'solr.delete() must not be called'

    @patch('pysolr.Solr')
    @td.with_wiki  # so there's some artifacts to reindex
    def test_solr_hosts_1(self, Solr):
        cmd = show_models.ReindexCommand('reindex')
        cmd.options, args = cmd.parser.parse_args([
            '-p', 'test', '--solr', '--solr-hosts=http://blah.com/solr/forge'])
        cmd._chunked_add_artifacts(list(range(10)))
        assert Solr.call_args[0][0] == 'http://blah.com/solr/forge'

    @patch('pysolr.Solr')
    def test_solr_hosts_list(self, Solr):
        cmd = show_models.ReindexCommand('reindex')
        cmd.options, args = cmd.parser.parse_args([
            '-p', 'test', '--solr', '--solr-hosts=http://blah.com/solr/forge,https://other.net/solr/forge'])
        cmd._chunked_add_artifacts(list(range(10)))
        # check constructors of first and second Solr() instantiations
        assert (
            {Solr.call_args_list[0][0][0], Solr.call_args_list[1][0][0]} ==
            {'http://blah.com/solr/forge',
                 'https://other.net/solr/forge'})

    @patch('allura.command.show_models.utils')
    def test_project_regex(self, utils):
        cmd = show_models.ReindexCommand('reindex')
        cmd.run([test_config, '--project-regex', '^test'])
        utils.chunked_find.assert_called_once_with(
            M.Project, {'shortname': {'$regex': '^test'}})

    @patch('allura.command.show_models.add_artifacts')
    def test_chunked_add_artifacts(self, add_artifacts):
        cmd = show_models.ReindexCommand('reindex')
        cmd.options = Mock(tasks=True, max_chunk=10 * 1000, ming_config=None)
        ref_ids = list(range(10 * 1000 * 2 + 20))
        cmd._chunked_add_artifacts(ref_ids)
        assert len(add_artifacts.post.call_args_list) == 3
        assert (
            len(add_artifacts.post.call_args_list[0][0][0]) == 10 * 1000)
        assert (
            len(add_artifacts.post.call_args_list[1][0][0]) == 10 * 1000)
        assert len(add_artifacts.post.call_args_list[2][0][0]) == 20

    @patch('allura.command.show_models.add_artifacts')
    def test_post_add_artifacts_too_large(self, add_artifacts):
        def on_post(chunk, **kw):
            if len(chunk) > 1:
                e = pymongo.errors.InvalidDocument(
                    "BSON document too large (16906035 bytes) - the connected server supports BSON document sizes up to 16777216 bytes.")
                # ming injects a 2nd arg with the document, so we do too
                e.args = e.args + ("doc:  {'task_name': 'allura.tasks.index_tasks.add_artifacts', ........",)
                raise e
        add_artifacts.post.side_effect = on_post
        cmd = show_models.ReindexCommand('reindex')
        cmd.options, args = cmd.parser.parse_args([])
        cmd._post_add_artifacts(list(range(5)))
        kw = {'update_solr': cmd.options.solr, 'update_refs': cmd.options.refs}
        expected = [
            call([0, 1, 2, 3, 4], **kw),
            call([0, 1], **kw),
            call([0], **kw),
            call([1], **kw),
            call([2, 3, 4], **kw),
            call([2], **kw),
            call([3, 4], **kw),
            call([3], **kw),
            call([4], **kw)
        ]
        assert expected == add_artifacts.post.call_args_list

    @patch('allura.command.show_models.add_artifacts')
    def test_post_add_artifacts_other_error(self, add_artifacts):
        def on_post(chunk, **kw):
            raise pymongo.errors.InvalidDocument("Cannot encode object...")
        add_artifacts.post.side_effect = on_post
        cmd = show_models.ReindexCommand('reindex')
        cmd.options = Mock(ming_config=None)
        with td.raises(pymongo.errors.InvalidDocument):
            cmd._post_add_artifacts(list(range(5)))

    @td.with_wiki  # so there's some artifacts to reindex
    def test_ming_config(self):
        cmd = show_models.ReindexCommand('reindex')
        cmd.run([test_config, '-p', 'test', '--tasks', '--ming-config', 'test.ini'])
