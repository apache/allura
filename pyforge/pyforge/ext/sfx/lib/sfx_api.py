import json
import httplib
from contextlib import closing

from tg import config
from pylons import c, request

from pyforge.lib.security import roles_with_project_access

class SFXProjectApi(object):

    def __init__(self):
        self.project_host = config.get('sfx.api.host', None)
        self.project_path = config.get('sfx.api.project_path', '/api/project')

    def _connect(self):
        return closing(httplib.HTTPConnection(self.project_host or request.host))

    def _unix_group_name(self, p):
        path = p.neighborhood.url_prefix + p.shortname
        parts = path.split('/')[1:]
        return '.'.join(reversed(parts))

    def create(self, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p)
            args = dict(
                user_id=c.user.sfx_userid,
                unix_group_name=ug_name,
                group_name=p.shortname,
                short_description=p.short_description)
            conn.request('POST', self.project_path, json.dumps(args))
            response = conn.getresponse()
            assert response.status == 201, \
                'Bad status from sfx create: %s' % (response.status)
            response.read()
            self.update(p)

    def read(self, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p)
            conn.request('GET', self.project_path + '/name/' + ug_name + '/json')
            response = conn.getresponse()
            assert response.status == 200, \
                'Bad status from sfx retrieve: %s' % (response.status)
            return json.loads(response.read())

    def update(self, p):
        with self._connect() as conn:
            ug_name = self._unix_group_name(p)
            args = dict(
                user_id=c.user.sfx_userid,
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
            ug_name = self._unix_group_name(p)
            conn.request('DELETE', self.project_path + '/' + ug_name)
            response = conn.getresponse()
            assert response.status in (200, 404, 410), \
                'Bad status from sfx update: %s' % (response.status)
