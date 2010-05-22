import json
import httplib
import urllib2
from contextlib import closing

from tg import config
from pylons import c, request

from pyforge import model as M
from pyforge.lib.security import roles_with_project_access

class SFXUserApi(object):
    
    def __init__(self):
        self.project_host = config.get('sfx.api.host', None)
        self.project_path = config.get('sfx.api.project_path', '/api/user')

    def _username_api_url(self, username):
        return 'http://%s/api/user/username/%s/json' % (
            self.project_host or request.host,
            username)

    def _userid_api_url(self, id):
        return 'http://%s/api/user/id/%s/json' % (
            self.project_host or request.host,
            id)

    def user_data(self, username, timeout=2):
        """
        given a sfnet hostname and userid, returns a dict of user data
        """
        try:
            url = self._userid_api_url(int(username))
        except ValueError:
            url = self._username_api_url(username)
        url_handle = urllib2.urlopen(url, timeout=timeout)
        return json.load(url_handle)['User']

    def upsert_user(self, username, user_data=None):
        if user_data is None:
            user_data = self.user_data(username)
        u = M.User.query.get(username=username)
        if u is None:
            u = M.User(
                username=username,
                display_name=user_data['name'],
                sfx_userid=user_data['id'])
            n = M.Neighborhood.query.get(name='Users')
            n.register_project('u/' + u.username, u, user_project=True)
        if u.display_name != user_data['name']:
            u.display_name = user_data['name']
        if u.sfx_userid != user_data['id']:
            u.sfx_userid = user_data['id']
        return u

class SFXProjectApi(object):

    def __init__(self):
        self.project_host = config.get('sfx.api.host', None)
        self.project_path = config.get('sfx.api.project_path', '/api/project')

    def _connect(self):
        return closing(httplib.HTTPConnection(self.project_host or request.host))

    def _unix_group_name(self, neighborhood, shortname):
        if neighborhood.url_prefix == 'p':
            path = shortname
        else:
            path = neighborhood.url_prefix + shortname[len(neighborhood.shortname_prefix):]
        parts = [ p for p in path.split('/') if p ]
        return '.'.join(reversed(parts))

    def create(self, user, neighborhood, shortname, short_description='No description'):
        with self._connect() as conn:
            ug_name = self._unix_group_name(neighborhood, shortname)
            args = dict(
                user_id=user.sfx_userid,
                unix_group_name=ug_name,
                group_name=shortname,
                short_description=short_description)
            conn.request('POST', self.project_path, json.dumps(args))
            response = conn.getresponse()
            assert response.status == 201, \
                'Bad status from sfx create: %s' % (response.status)
            return response.read()

    def read(self, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p.neighborhood, p.shortname)
            conn.request('GET', self.project_path + '/name/' + ug_name + '/json')
            response = conn.getresponse()
            assert response.status == 200, \
                'Bad status from sfx retrieve: %s' % (response.status)
            return json.loads(response.read())

    def update(self, user, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p.neighborhood, p.shortname)
            args = dict(
                user_id=user.sfx_userid,
                group_name=p.shortname,
                short_description=p.short_description,
                developers = [
                    pr.user.sfx_userid
                    for pr in roles_with_project_access('update', p)
                    if pr.user is not None and pr.user.sfx_userid is not None ])
            conn.request('PUT', self.project_path + '/' + ug_name, json.dumps(args))
            response = conn.getresponse()
            assert response.status == 200, \
                'Bad status from sfx update: %s' % (response.status)
            response.read()

    def delete(self, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p.neighborhood, p.shortname)
            conn.request('DELETE', self.project_path + '/' + ug_name)
            response = conn.getresponse()
            assert response.status in (200, 404, 410), \
                'Bad status from sfx update: %s' % (response.status)
