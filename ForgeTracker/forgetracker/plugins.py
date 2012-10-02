import logging

from tg import config
from pylons import app_globals as g

log = logging.getLogger(__name__)


class ImportIdConverter(object):
    '''
    An interface to provide authentication services for Allura.

    To provide a new converter, expose an entry point in setup.py:

        [allura.tickets.import_id_converter]
        mylegacy = foo.bar:LegacyConverter

    Then in your .ini file, set tickets.import_id_converter=mylegacy
    '''

    @classmethod
    def get(cls):
        converter = config.get('tickets.import_id_converter')
        if converter:
            return g.entry_points['allura.tickets.import_id_converter'][converter]()
        return cls()

    def simplify(self, import_id):
        return import_id

    def expand(self, url_part, app_instance):
        return url_part
