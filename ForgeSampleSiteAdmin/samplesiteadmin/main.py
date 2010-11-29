import os
import difflib
import logging
from pprint import pformat
from datetime import datetime, timedelta

from pylons import c, g
import pkg_resources
from pylons import c, request
from tg import expose, redirect, flash
from webob import exc
from pymongo.bson import ObjectId


from ming.orm import session
from allura import version
from allura.app import Application, WidgetController, ConfigOption, SitemapEntry
from allura.lib import helpers as h
from allura.ext.project_home import model as M
from allura.lib.security import require, has_project_access, has_artifact_access
from allura.model import User, ArtifactLink
from allura.model import ApiToken
from allura.controllers import BaseController

log = logging.getLogger(__name__)


class SampleSiteAdminApp(Application):
    __version__ = version.__version__
    installable = True
    tool_label='Sample Site Admin'
    default_mount_label='SiteAdmin'
    default_mount_point='site'
    status='user'

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = SiteAdminController()

    def admin_menu(self):
        return []

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            for perm in self.permissions:
                self.config.acl[perm] = [ pr._id ]

    def uninstall(self, project): # pragma no cover
        raise NotImplementedError, "uninstall"

class SiteAdminController(BaseController):

    def _check_security(self):
        # Only user to whom this tool was added may access it
        if c.project.shortname != 'u/' + c.user.username:
            raise exc.HTTPForbidden()

    @expose('jinja:sample_site_admin.html')
    def index(self):
        return {}

    @expose('jinja:user_special_api_keys.html')
    def api_keys(self, **data):
        import json
        import dateutil.parser
        if request.method == 'POST':
            log.info('api_keys: %s', data)
            ok = True
            for_user = User.by_username(data['for_user'])
            if not for_user:
                ok = False
                flash('User not found')
            caps = None
            try:
                caps = json.loads(data['caps'])
            except ValueError:
                ok = False
                flash('JSON format error')
            if type(caps) is not type({}):
                ok = False
                flash('Capabilities must be a dictionary, mapping capability name to optional discriminator(s) (or "")')
            try:
                expires = dateutil.parser.parse(data['expires'])
            except ValueError:
                ok = False
                flash('Date format error')
                
            if ok:
                tok = None
                try:
                    tok = ApiToken(user_id=for_user._id, capabilities=caps, expires=expires)
                    session(tok).flush()
                    log.info('New token: %s', tok)
                except:
                    log.exception('Could not create API key:')
                    flash('Error creating API key')
        else:
            data = {'expires': datetime.utcnow() + timedelta(days=1)}

        username = c.project.shortname.split('/')[1]
        data['user'] = User.by_username(username)
        data['token_list'] = ApiToken.query.find(dict(expires={'$ne': None})).all()
        return data
