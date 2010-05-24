import os
import mimetypes
import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc

from pylons import c, g
from pyforge.lib import helpers as h
from pyforge import model as M

class StaticController(object):
    '''Controller for mounting static resources in tools by the tool
    name'''

    @expose()
    def _lookup(self, ep_name, *remainder):
        for ep in pkg_resources.iter_entry_points('pyforge', ep_name):
            result = StaticAppController(ep)
            # setattr(self, ep_name, result)
            return result, ['default'] + list(remainder)
        raise exc.HTTPNotFound, ep_name

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
        

class StaticAppController(object):

    def __init__(self, ep):
        self.ep = ep
        self.fn = pkg_resources.resource_filename(
            ep.module_name, 'nf/%s' % ep.name)

    @expose()
    def default(self, *args):
        # Stick the !@#$!@ extension back on args[-1]
        fn = request.path.rsplit('/', 1)[-1]
        ext = fn.rsplit('.', 1)[-1]
        args = list(args[:-1]) + [ args[-1] + '.' + ext ]
        path = os.path.join(self.fn, '/'.join(args))
        mtype, menc = mimetypes.guess_type(path)
        if mtype:
            response.headers['Content-Type'] = mtype
        if menc: # pragma no cover
            response.headers['Content-Encoding'] = menc
        try:
            return open(path, 'rb')
        except IOError:
            raise exc.HTTPNotFound, request.path
