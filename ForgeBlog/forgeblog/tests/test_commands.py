from pylons import c, g

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from allura import model as M
from allura.lib import security
from allura.lib import helpers as h
from forgeblog import model as BM
from forgeblog.command import rssfeeds

test_config = 'test.ini#main'

def setUp():
    setup_basic_test()
    setup_global_objects()

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
