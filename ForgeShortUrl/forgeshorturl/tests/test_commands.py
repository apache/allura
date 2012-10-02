from nose.tools import assert_equal
from alluratest.controller import setup_basic_test, setup_global_objects
from forgeshorturl.command import migrate_urls
from forgeshorturl.model import ShortUrl
from allura import model as M
from mock import patch, MagicMock, Mock

test_config = 'test.ini#main'


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()


class TableMock(MagicMock):

    def select(self):
        m = Mock()
        m.execute = self.execute
        return m

    def execute(self):
        test_urls = [
            {
                'short_id': 'g',
                'url': 'http://google.com',
                'description': 'Two\nlines',
                'private': 'N',
                'create_time': 1,
                'edit_time': 2,
                'create_user': 1
            },
            {
                'short_id': 'y',
                'url': 'http://yahoo.com',
                'description': 'One line',
                'private': 'Y',
                'create_time': 3,
                'edit_time': 4,
                'create_user': 1
            }
        ]
        for url in test_urls:
            yield url


@patch('sqlalchemy.Table', TableMock)
def test_migrate_urls():
    p = M.Project.query.find().first()
    app = p.app_instance('url')
    if not app:
        app = p.install_app('ShortUrl')
    assert_equal(ShortUrl.query.find({'app_config_id': app.config._id}).count(), 0)

    cmd = migrate_urls.MigrateUrls('migrate-urls')
    cmd.run([test_config, 'db_name', str(p._id)])
    assert_equal(ShortUrl.query.find({'app_config_id': app.config._id}).count(), 2)

    u = ShortUrl.query.find(dict(app_config_id=app.config._id, short_name='g')).first()
    assert_equal(u.full_url, 'http://google.com')
    assert_equal(u.description, 'Two\nlines')
    assert not u.private
    assert_equal(u.create_user, M.User.anonymous()._id)

    u = ShortUrl.query.find(dict(app_config_id=app.config._id, short_name='y')).first()
    assert_equal(u.full_url, 'http://yahoo.com')
    assert_equal(u.description, 'One line')
    assert u.private
    assert_equal(u.create_user, M.User.anonymous()._id)
