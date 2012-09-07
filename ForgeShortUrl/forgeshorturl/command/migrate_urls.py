import tg
from bson import ObjectId
from forgeshorturl.command.base import ShortUrlCommand
from forgeshorturl.model import ShortUrl
from allura.lib import exceptions
from allura.lib import helpers as h
from allura import model as M
from ming.orm import session
import sqlalchemy
from datetime import datetime


class MigrateUrls(ShortUrlCommand):
    """Usage example:

    paster migrate-urls ../Allura/development.ini urls 504867768fd0920bb8c21ffd
    """
    min_args = 3
    max_args = 3
    usage = '<ini file> <database name> <project>'
    summary = ('Migrate short urls from MySQL tables to ShortUrlApp\n'
            '\t<database name> - MySQL database name to load data from\n'
            '\t\tthe rest of the connection information comes from ini file:\n'
            '\t\t\tsfx.hostedapps_db.hostname - database hostname\n'
            '\t\t\tsfx.hostedapps_db.port - database port\n'
            '\t\t\tsfx.hostedapps_db.username - database username\n'
            '\t\t\tsfx.hostedapps_db.password - user password\n'
            '\t<project> - the project id to load data to\n')
    parser = ShortUrlCommand.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        p_id = self.args[2]
        p = M.Project.query.get(_id=ObjectId(p_id))
        if not p:
            raise exceptions.NoSuchProjectError('The project %s '
                    'could not be found in the database' % p_id)

        db = sqlalchemy.create_engine(self._connection_string())
        meta = sqlalchemy.MetaData()
        meta.bind = db
        urls = sqlalchemy.Table('sfurl', meta, autoload=True)

        for row in urls.select().execute():
            url = ShortUrl.upsert(h.really_unicode(row['short_id']))
            url.url = h.really_unicode(row['url'])
            url.description = h.really_unicode(row['description'])
            url.private = row['private'] == 'Y'
            url.created = datetime.fromtimestamp(row['create_time'])
            url.last_updated = datetime.fromtimestamp(row['edit_time'])
            url.project_id = p._id
            user = M.User.query.get(sfx_userid=row['create_user'])
            user_id = user._id if user else M.User.anonymous()._id
            url.create_user = user_id

        session(ShortUrl).flush()

    def _connection_string(self):
        prefix = 'sfx.hostedapps_db.'
        params = {
            'host': tg.config.get(prefix + 'hostname', 'localhost'),
            'port': tg.config.get(prefix + 'port', 3306),
            'user': tg.config.get(prefix + 'username', ''),
            'pwd': tg.config.get(prefix + 'password', ''),
            'db': self.args[1]
        }
        return 'mysql://%(user)s:%(pwd)s@%(host)s:%(port)s/%(db)s' % params
