from alluratest.controller import setup_basic_test, setup_global_objects
from forgeshorturl.command import migrate_urls
from forgeshorturl.model import ShortUrl
from allura import model as M
from mock import patch, MagicMock, Mock
import datetime
import time

test_config = 'test.ini#main'
fmt = '%Y-%m-%d %H:%M'


def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()


class TableMock(MagicMock):

    def _make_timestamp(self, date):
        d = datetime.datetime.strptime(date, fmt)
        return time.mktime(d.timetuple())

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
                'create_time': self._make_timestamp('2012-09-01 10:00'),
                'edit_time': self._make_timestamp('2012-09-01 12:30'),
                'create_user': 1
            },
            {
                'short_id': 'y',
                'url': 'http://yahoo.com',
                'description': 'One line',
                'private': 'Y',
                'create_time': self._make_timestamp('2012-09-02 10:00'),
                'edit_time': self._make_timestamp('2012-09-02 12:30'),
                'create_user': 1
            }
        ]
        for url in test_urls:
            yield url


@patch('sqlalchemy.Table', TableMock)
def test_migrate_urls():
    p = M.Project.query.find().first()
    assert ShortUrl.query.find({'project_id': p._id}).count() == 0

    cmd = migrate_urls.MigrateUrls('migrate-urls')
    cmd.run([test_config, 'db_name', str(p._id)])
    assert ShortUrl.query.find({'project_id': p._id}).count() == 2

    u = ShortUrl.query.get(short_name='g')
    assert u.url == 'http://google.com'
    assert u.description == 'Two\nlines'
    assert not u.private
    assert u.created == datetime.datetime.strptime('2012-09-01 10:00', fmt)
    assert u.last_updated == (datetime.datetime
                                      .strptime('2012-09-01 12:30', fmt))
    assert u.create_user == M.User.anonymous()._id

    u = ShortUrl.query.get(short_name='y')
    assert u.url == 'http://yahoo.com'
    assert u.description == 'One line'
    assert u.private
    assert u.created == datetime.datetime.strptime('2012-09-02 10:00', fmt)
    assert u.last_updated == (datetime.datetime
                                      .strptime('2012-09-02 12:30', fmt))
    assert u.create_user == M.User.anonymous()._id
