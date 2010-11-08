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

    @expose(content_type='text/css')
    @without_trailing_slash
    def site_style(self, **kw):
        """Display the css for the default theme."""
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        response.headers['Content-Type'] = ''
        response.content_type = 'text/css'
        utils.cache_forever()
        params = dict(color1=theme.color1,
                      color2=theme.color2,
                      color3=theme.color3,
                      color4=theme.color4,
                      color5=theme.color5,
                      color6=theme.color6,
                      g=g)
        css = g.jinja2_env.get_template(g.theme['base_css']).render(extra_css='', **params)
        for t in g.theme['theme_css']:
            css = css + '\n' + g.jinja2_env.get_template(t).render(**params)
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

    @expose()
    @with_trailing_slash
    def redirect(self, path, **kw):
        """Redirect to external sites."""
        redirect(path)
