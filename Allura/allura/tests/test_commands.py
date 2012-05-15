import mock
from nose.tools import assert_raises
from datadiff.tools import assert_equal
import pylons

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura.command import script, set_neighborhood_level, set_neighborhood_private, rssfeeds
from allura import model as M
from forgeblog import model as BM

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

def test_pull_rss_feeds():
    base_app =  M.AppConfig.query.find().all()[0]
    tmp_app = M.AppConfig(tool_name=u'Blog', discussion_id=base_app.discussion_id,
                          project_id=base_app.project_id,
                          options={u'ordinal': 0, u'show_right_bar': True,
                                    u'project_name': base_app.project.name,
                                    u'mount_point': u'blog',
                                    u'mount_label': u'Blog'})
    new_external_feeds = ['http://wordpress.org/news/feed/']
    BM.Globals(app_config_id=tmp_app._id, external_feeds=new_external_feeds)
    ThreadLocalORMSession.flush_all()

    cmd = rssfeeds.RssFeedsCommand('pull-rss-feeds')
    cmd.run([test_config, '-a', tmp_app._id])
    cmd.command()

    assert len(BM.BlogPost.query.find({'app_config_id': tmp_app._id}).all()) > 0
