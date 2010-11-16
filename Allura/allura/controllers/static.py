import os
import mimetypes
import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc

from pylons import c, g
from allura.lib import helpers as h
from allura.lib import utils
from allura import model as M

class NewForgeController(object):

    @expose()
    @without_trailing_slash
    def markdown_to_html(self, markdown, project=None, app=None):
        """Convert markdown to html."""
        if project:
            g.set_project(project)
            if app:
                g.set_app(app)
        html = g.markdown.convert(markdown)
        return html

    @expose()
    @with_trailing_slash
    def redirect(self, path, **kw):
        """Redirect to external sites."""
        redirect(path)
