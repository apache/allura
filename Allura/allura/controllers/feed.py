#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from tg import expose, validate, request, response
from tg.decorators import without_trailing_slash
from formencode import validators as V
from tg import tmpl_context as c
from webob import exc

from allura import model as M
from allura.lib import helpers as h


class FeedArgs:

    """A facade for the arguments required by
    :meth:`allura.model.artifact.Feed.feed`.

    Used by :meth:`FeedController.feed` to create a real feed.

    """

    def __init__(self, query, title, url, description=None):
        """
        :param query: mongo criteria to query the Feed collection.
                      Pagination & filter criteria will be added in automatically
                      Can be a function to return criteria, which will be passed args (since, until, page, limit) for
                        advanced optimization.
        :param title: feed title
        :param url: feed's own url
        :param description: feed description
        """
        self.query = query
        self.title = title
        self.url = url
        self.description = description or title


class FeedController:

    """Mixin class which adds RSS and Atom feed endpoints to an existing
    controller.

    Feeds will be accessible at the following URLs:

        http://host/path/to/controller/feed -> RSS
        http://host/path/to/controller/feed.rss -> RSS
        http://host/path/to/controller/feed.atom -> Atom

    A default feed is provided by :meth:`get_feed`. Subclasses that need
    a customized feed should override :meth:`get_feed`.

    """
    FEED_TYPES = ['.atom', '.rss']
    FEED_NAMES = [str(f'feed{typ}') for typ in FEED_TYPES]

    def __getattr__(self, name):
        if name in self.FEED_NAMES:
            return self.feed
        raise AttributeError(name)

    def _get_feed_type(self, request):
        for typ in self.FEED_TYPES:
            if request.environ['PATH_INFO'].endswith(typ):
                return typ.lstrip('.')
        return 'rss'

    @without_trailing_slash
    @expose()
    @validate(dict(
        since=h.DateTimeConverter(if_empty=None, if_invalid=None),
        until=h.DateTimeConverter(if_empty=None, if_invalid=None),
        page=V.Int(if_empty=None, if_invalid=None),
        limit=V.Int(if_empty=None, if_invalid=None)))
    def feed(self, since=None, until=None, page=None, limit=None, **kw):
        """Return a utf8-encoded XML feed (RSS or Atom) to the browser.
        """
        feed_def = self.get_feed(c.project, c.app, c.user)
        if not feed_def:
            raise exc.HTTPNotFound
        feed = M.Feed.feed(
            feed_def.query,
            self._get_feed_type(request),
            feed_def.title,
            feed_def.url,
            feed_def.description,
            since, until, page, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    def get_feed(self, project, app, user):
        """Return a default :class:`FeedArgs` for this controller.

        Subclasses should override to customize the feed.

        :param project: :class:`allura.model.project.Project`
        :param app: :class:`allura.app.Application`
        :param user: :class:`allura.model.auth.User`
        :rtype: :class:`FeedArgs`

        """
        return FeedArgs(
            dict(project_id=project._id, app_config_id=app.config._id),
            'Recent changes to %s' % app.config.options.mount_point,
            app.url)
