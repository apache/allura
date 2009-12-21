import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.reactors import common_react

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestReact(TestCase):

    def setUp(self):
        g._push_object(app_globals.Globals())
        c._push_object(EmptyClass())
        c.project = M.Project.query.get(_id='projects/test/')
        c.app = c.project.app_instance('src')

    def publish(self, func, routing_key, data=None):
        if data is None: data = {}
        d = dict(data)
        d.update(project_id=c.project._id,
                 mount_point=c.app.config.options.mount_point)
        return func(routing_key, d)

    def test_initialized(self):
        self.publish(common_react.initialized, 'scm.initialized')

    def test_forked_update(self):
        repo = dict(project_id=c.project._id,
                    app_config_id=c.app.config._id)
        self.publish(
            common_react.forked_update_source, 'scm.initialized',
            dict(forked_from=repo, forked_to=repo))
        self.publish(
            common_react.forked_update_dest, 'scm.initialized',
            dict(forked_from=repo, forked_to=repo))

    def test_cloned(self):
        self.publish(common_react.cloned, 'scm.cloned', dict(
                url='forgescm/tests/hg_repo'))
                    
