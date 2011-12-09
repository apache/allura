import os
import mimetypes
import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc

from pylons import c, g
from allura.lib import helpers as h
from allura import model as M

class NewForgeController(object):

    @expose()
    @without_trailing_slash
    def markdown_to_html(self, markdown, neighborhood=None, project=None, app=None):
        """Convert markdown to html."""
        if neighborhood is None or project is None:
            raise exc.HTTPBadRequest()
        h.set_context(project, app, neighborhood=neighborhood)
        html = g.markdown_wiki.convert(markdown)
        return html

    @expose()
    @with_trailing_slash
    def redirect(self, path, **kw):
        """Redirect to external sites."""

        # Make sure the url can be encoded to iso-8859-1 (required for HTTP
        # headers. If it can't, urlquote it first, then redirect. Allows us to
        # redirect to external links in markdown, even if the url contains
        # unquoted unicode chars.
        try:
            path.encode('ISO-8859-1')
        except UnicodeEncodeError:
            i = path.find('://')
            if i > -1:
                scheme = path[:i+3]
                path = path[i+3:]
            else:
                scheme = ''
            path = scheme + h.urlquote(path)
        redirect(path)

