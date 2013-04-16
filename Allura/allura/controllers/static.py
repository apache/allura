import os
import mimetypes
import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc

from pylons import tmpl_context as c, app_globals as g
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

        if app == 'wiki':
            html = g.markdown_wiki.convert(markdown)
        else:
            html = g.markdown.convert(markdown)
        return html
