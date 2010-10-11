import re
import json
import httplib
import urllib
import urllib2
import logging
from contextlib import closing

from tg import config
from pylons import c, request

from allura import model as M
from allura.lib.security import roles_with_project_access
from . import exceptions as sfx_exc
from sfx.model import tables as T

log = logging.getLogger(__name__)

def read_response(response, *expected):
    if not expected: expected = (200,)
    text = response.read()
    if response.status in expected:
        try:
            return json.loads(text)
        except ValueError:
            return text
    cls = sfx_exc.SFXAPIError.status_map.get(response.status, sfx_exc.SFXAPIError)
    raise cls('Error status %s' % response.status)

class SFXUserApi(object):

    def __init__(self):
        self.project_host = config.get('sfx.api.host', None)
        self.project_path = config.get('sfx.api.project_path', '/api/user')

    def _username_api_url(self, username):
        return 'http://%s/api/user/username/%s/json' % (
            urllib.quote(self.project_host or request.host),
            username)

    def _userid_api_url(self, id):
        return 'http://%s/api/user/id/%s/json' % (
            urllib.quote(self.project_host or request.host),
            id)

    def user_data(self, username, timeout=2):
        """
        given a sfnet hostname and userid, returns a dict of user data
        """
        try:
            url = self._userid_api_url(int(username))
        except ValueError:
            url = self._username_api_url(username)
        try:
            url_handle = urllib2.urlopen(url, timeout=timeout)
            return json.load(url_handle)['User']
        except urllib2.HTTPError, ex:
            if ex.code == 404: return None
            raise

    def upsert_user(self, username, user_data=None):
        un = re.escape(username)
        un = un.replace(r'\_', '[-_]')
        un = un.replace(r'\-', '[-_]')
        rex = re.compile('^' + un + '$')
        u = M.User.query.get(username=rex)
        if user_data is None:
            if u is not None and u.get_tool_data('sfx', 'userid'):
                user_data = self.user_data(u.get_tool_data('sfx', 'userid'))
            else:
                user_data = self.user_data(username)
        if u is None:
            if user_data is None: return None
            u = M.User(
                username=username,
                display_name=user_data['name'])
            u.set_tool_data('sfx', userid=user_data['id'])
            n = M.Neighborhood.query.get(name='Users')
            try:
                n.register_project('u/' + u.username.replace('_', '-'), u, user_project=True)
            except sfx_exc.exceptions.ProjectConflict:
                log.error('Conflict (user project already created): u/%s', u.username.replace('_', '-'))
        if user_data is None: return u
        if u.get_tool_data('sfx', 'userid') != user_data['id']:
            u.set_tool_data('sfx', userid=user_data['id'])
        if u.display_name != user_data['name']:
            u.display_name = user_data['name']
        u.set_tool_data('sfx', userid=user_data['id'])
        u_row = (
            T.users.select(
                whereclause=T.users.c.user_id==user_data['id'])
            .execute()
            .fetchone())
        u.claim_only_addresses(u_row.email, user_data['sf_email'])
        if u.preferences.email_address != user_data['sf_email']:
            u.preferences.email_address = user_data['sf_email']
        return u

class SFXProjectApi(object):

    def __init__(self):
        self.project_host = config.get('sfx.api.host', None)
        self.project_path = config.get('sfx.api.project_path', '/api/project')

    def _connect(self):
        return closing(httplib.HTTPConnection(self.project_host or request.host))

    def _unix_group_name(self, neighborhood, shortname):
        path = neighborhood.url_prefix + shortname[len(neighborhood.shortname_prefix):]
        parts = [ p for p in path.split('/') if p ]
        if len(parts) == 2 and parts[0] == 'p':
            parts = parts[1:]
        return '.'.join(reversed(parts))

    def create(self, user, neighborhood, shortname, short_description='No description'):
        with self._connect() as conn:
            ug_name = self._unix_group_name(neighborhood, shortname)
            log.info('%s creating project %s', user.username, ug_name)
            args = dict(
                user_id=user.get_tool_data('sfx', 'userid'),
                unix_group_name=ug_name,
                group_name=shortname,
                short_description=short_description)
            conn.request('POST', self.project_path, json.dumps(args))
            response = conn.getresponse()
            r = read_response(response, 201)
            return ug_name

    def read(self, p):
        with self._connect() as conn:
            ug_name = p.get_tool_data('sfx', 'unix_group_name')
            if ug_name is None:
                ug_name = self._unix_group_name(p.neighborhood, p.shortname)
                p.set_tool_data('sfx', unix_group_name=ug_name)
            conn.request('GET', self.project_path + '/name/' + ug_name + '/json')
            response = conn.getresponse()
            r = read_response(response)
            p.set_tool_data('sfx', group_id=r['Project']['id'])
            return r

    def update(self, user, p):
        with self._connect() as conn:
            ug_name = p.get_tool_data('sfx', 'unix_group_name')
            log.info('%s updating project %s', user.username, ug_name)
            if ug_name is None:
                ug_name = self._unix_group_name(p.neighborhood, p.shortname)
                p.set_tool_data('sfx', unix_group_name=ug_name)
            args = dict(
                user_id=user.tool_data.sfx.userid,
                group_name=p.name.encode('utf-8'),
                short_description=p.short_description,
                developers = [
                    pr.user.get_tool_data('sfx', 'userid')
                    for pr in roles_with_project_access('update', p)
                    if pr.user is not None and pr.user.get_tool_data('sfx', 'userid') is not None ])
            args['admins'] = args['developers']
            conn.request('PUT', self.project_path + '/' + ug_name, json.dumps(args))
            response = conn.getresponse()
            return read_response(response)

    def delete(self, user, p):
        with self._connect() as conn:
            ug_name = p.get_tool_data('sfx', 'unix_group_name')
            log.info('%s deleting project %s', user.username, ug_name)
            if ug_name is None:
                ug_name = self._unix_group_name(p.neighborhood, p.shortname)
                p.set_tool_data('sfx', unix_group_name=ug_name)
            args = dict(
                user_id=user.get_tool_data('sfx', 'userid'))
            conn.request('DELETE', self.project_path + '/' + ug_name, json.dumps(args))
            response = conn.getresponse()
            return read_response(response, 200,404,410)
