import difflib
import logging
from datetime import datetime, timedelta
from pprint import pformat

import pkg_resources
from pylons import c, g, request
from tg import expose, redirect, validate
from tg.decorators import with_trailing_slash
from formencode import validators as V
from pymongo.bson import ObjectId

from pyforge.app import Application, ConfigOption, SitemapEntry
from pyforge import version
from pyforge.model import ProjectRole, SearchConfig, ScheduledMessage, Artifact, Tag, UserTags
from pyforge.lib.helpers import push_config
from pyforge.lib.security import require, has_artifact_access
from pyforge.lib.decorators import audit, react
from pyforge.lib import search

log = logging.getLogger(__name__)

class TagApp(Application):
    __version__ = version.__version__
    installable = False

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = None
        self.templates = None
        self.sitemap = None

    @classmethod
    @react('tag.event')
    def tag_event(cls, routing_key, doc):
        aref = doc['artifact_ref']
        aref['project_id'] = ObjectId(str(aref['project_id']))
        artifact = Artifact.load_ref(aref)
        g.set_app(aref['mount_point'])
        if doc['event'] == 'add':
            artifact.add_tags(doc['tags'])
            UserTags.upsert(c.user, aref).add_tags(doc['when'], doc['tags'])
            Tag.add(aref, doc['tags'])
        elif doc['event'] == 'remove':
            artifact.remove_tags(doc['tags'])
            UserTags.upsert(c.user, aref).remove_tags(doc['tags'])
            Tag.remove(aref, doc['tags'])

    def sidebar_menu(self):
        return [ ]

    def install(self, project):
        pass # pragma no cover

    def uninstall(self, project):
        pass # pragma no cover

