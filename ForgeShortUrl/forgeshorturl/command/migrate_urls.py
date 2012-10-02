import tg
import warnings
from pylons import tmpl_context as c
import bson
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

    paster migrate-urls ../Allura/development.ini sfurl allura.p

    The following settings are read from the INI file:

        sfx.hostedapps_db.hostname
        sfx.hostedapps_db.port
        sfx.hostedapps_db.username
        sfx.hostedapps_db.password
    """
    min_args = 3
    max_args = 3
    usage = '<ini file> <database name> <project name>'
    summary = 'Migrate short URLs from the SFX Hosted App to Allura'
    parser = ShortUrlCommand.standard_parser(verbose=True)
    parser.add_option('-m', dest='mount_point', type='string', default='url',
                      help='mount point (default: url)')
    parser.add_option('-n', dest='nbhd', type='string', default='p',
                      help='neighborhood shortname or _id (default: p)')
    parser.add_option('--clean', dest='clean', action='store_true', default=False,
                      help='clean existing short URLs from Allura')

    def command(self):
        self._setup()
        self._load_objects()

        if self.options.clean:
            ShortUrl.query.remove({'app_config_id': c.app.config._id})

        for row in self.urls.select().execute():
            url = ShortUrl.upsert(h.really_unicode(row['short_id']))
            url.full_url = h.really_unicode(row['url'])
            url.description = h.really_unicode(row['description'])
            url.private = row['private'] == 'Y'
            url.created = datetime.utcfromtimestamp(row['create_time'])
            url.last_updated = datetime.utcfromtimestamp(row['edit_time'])
            user = M.User.query.find({'tool_data.sfx.userid': row['create_user']}).first()
            url.create_user = user._id if user else M.User.anonymous()._id

        session(ShortUrl).flush()

    def _setup(self):
        '''Perform basic setup, suppressing superfluous warnings.'''
        with warnings.catch_warnings():
            try:
                from sqlalchemy import exc
            except ImportError:
                pass
            else:
                warnings.simplefilter("ignore", category=exc.SAWarning)
            self.basic_setup()

        db = sqlalchemy.create_engine(self._connection_string())
        meta = sqlalchemy.MetaData()
        meta.bind = db
        self.urls = sqlalchemy.Table('sfurl', meta, autoload=True)

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

    def _load_objects(self):
        nbhd = None
        try:
            nbhd = M.Neighborhood.query.get(_id=bson.ObjectId(self.options.nbhd))
        except bson.errors.InvalidId:
            nbhd = M.Neighborhood.query.find({'$or': [
                {'url_prefix': '/%s/' % self.options.nbhd},
                {'name': self.options.nbhd},
            ]}).first()
        assert nbhd, 'Neighborhood %s not found' % self.options.nbhd
        try:
            c.project = M.Project.query.get(_id=bson.ObjectId(self.args[2]))
        except bson.errors.InvalidId:
            c.project = M.Project.query.find({'$or': [
                {'shortname': self.args[2]},
                {'name': self.args[2]},
            ]}).first()
        if not c.project:
            raise exceptions.NoSuchProjectError('The project %s '
                    'could not be found in the database' % self.args[2])
        c.app = c.project.app_instance(self.options.mount_point)
        assert c.app, 'Project does not have ShortURL app installed'
