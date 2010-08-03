# -*- coding: utf-8 -*-
"""REST Controller"""
import logging

from webob import exc
from tg import expose
from pylons import c, request

from pyforge import model as M
from pyforge.lib import helpers as h

log = logging.getLogger(__name__)
action_logger = h.log_action(log, 'API:')

class RestController(object):

    def _authenticate_request(self):
        'Based on request.params, authenticate the request'
        if 'api_key' not in request.params: return M.User.anonymous()
        api_key = request.params.get('api_key')
        api_token = M.ApiToken.query.get(api_key=api_key)
        if api_token is not None and api_token.authenticate_request(request.path, request.params):
            return api_token.user
        else:
            raise exc.HTTPForbidden

    @expose()
    def _lookup(self, name, *remainder):
        c.user = self._authenticate_request()
        neighborhood = M.Neighborhood.query.get(url_prefix = '/' + name + '/')
        if not neighborhood: raise exc.HTTPNotFound, name
        return NeighborhoodRestController(neighborhood), remainder

class NeighborhoodRestController(object):

    def __init__(self, neighborhood):
        self._neighborhood = neighborhood

    @expose()
    def _lookup(self, name, *remainder):
        if not h.re_path_portion.match(name):
            raise exc.HTTPNotFound, name
        name = self._neighborhood.shortname_prefix + name
        project = M.Project.query.get(shortname=name, neighborhood_id=self._neighborhood._id, deleted=False)
        if not project: raise exc.HTTPNotFound, name
        c.project = project
        return ProjectRestController(), remainder

class ProjectRestController(object):

    @expose()
    def _lookup(self, name, *remainder):
        if not h.re_path_portion.match(name):
            raise exc.HTTPNotFound, name
        subproject = M.Project.query.get(shortname=c.project.shortname + '/' + name, deleted=False)
        if subproject:
            c.project = subproject
            c.app = None
            return ProjectRestController(), remainder
        app = c.project.app_instance(name)
        if app is None:
            raise exc.HTTPNotFound, name
        c.app = app
        if app.api_root is None:
            raise exc.HTTPNotFound, name
        action_logger.info('', extra=dict(
                api_key=request.params.get('api_key')))
        return app.api_root, remainder


