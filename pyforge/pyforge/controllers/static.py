import os
import mimetypes
import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc

from pylons import c, g
from pyforge.lib import helpers as h
from pyforge import model as M

class NewForgeController(object):

    @expose()
    @without_trailing_slash
    def site_style(self):
        """Display the css for the default theme."""
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        colors = dict(color1=theme.color1,
                      color2=theme.color2,
                      color3=theme.color3,
                      color4=theme.color4,
                      color5=theme.color5,
                      color6=theme.color6)
        tpl_fn = pkg_resources.resource_filename(
            'pyforge', 'templates/style.css')
        css = h.render_genshi_plaintext(tpl_fn,**colors)
        response.headers['Content-Type'] = ''
        response.content_type = 'text/css'
        return css

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
        
