import os
from unittest import TestCase
from pylons import c, g
import ming
from pyforge import model as M
from pyforge.lib import app_globals
from forgescm.lib import hg
from forgescm import model as FM

ming.configure(**{'ming.main.master':'mongo://localhost:27017/pyforge'})

class EmptyClass(object): pass

class TestHgLogParser(TestCase):

    def setUp(self):
        path = os.path.join(
            os.path.dirname(__file__),
            'hg.log')
        self.fp = open(path)
        c._push_object(EmptyClass())
        c.project = M.Project.m.get(_id='projects/test/')
        c.app = c.project.app_instance('src')
        g._push_object(app_globals.Globals())
        FM.Commit.m.remove(dict(app_conf_id=c.app.config._id))
        FM.Patch.m.remove(dict(app_conf_id=c.app.config._id))

    def test_parse(self):
        parser = hg.LogParser(c.app.repo._id)
        commits = parser.feed(self.fp)
        for ct in commits:
            print ct
            

