# -*- coding: utf-8 -*-
"""
Global configuration file for TG2-specific settings in allura.

This file complements development/deployment.ini.

Please note that **all the argument values are strings**. If you want to
convert them into boolean, for example, you should use the
:func:`paste.deploy.converters.asbool` function, as in::
    
    from paste.deploy.converters import asbool
    setting = asbool(global_conf.get('the_setting'))
 
"""
import logging
import pkg_resources

import tg
import jinja2
from tg.configuration import AppConfig, config
from routes import Mapper
from webhelpers.html import literal

import ew

import allura
# needed for tg.configuration to work
from allura.lib import app_globals

log = logging.getLogger(__name__)

class ForgeConfig(AppConfig):

    def __init__(self, root_controller='root'):
        AppConfig.__init__(self)
        self.root_controller = root_controller
        self.package = allura
        self.renderers = [ 'json', 'genshi', 'mako', 'jinja' ]
        self.default_renderer = 'genshi'
        self.use_sqlalchemy = False
        self.use_toscawidgets = True
        self.use_transaction_manager = False
        # self.handle_status_codes = [ 403, 404 ]
        self.handle_status_codes = [ 403, 404 ]

    def after_init_config(self):
        config['pylons.strict_c'] = True

    def setup_routes(self):
        map = Mapper(directory=config['pylons.paths']['controllers'],
                     always_scan=config['debug'])
        # Setup a default route for the root of object dispatch
        map.connect('*url', controller=self.root_controller,
                    action='routes_placeholder')
        config['routes.map'] = map

    def setup_jinja_renderer(self):
        config['pylons.app_globals'].jinja2_env = jinja2.Environment(
            loader=PackagePathLoader(),
            auto_reload=self.auto_reload_templates,
            autoescape=True,
            extensions=['jinja2.ext.do'])
        # Jinja's unable to request c's attributes without strict_c
        config['pylons.strict_c'] = True
        self.render_functions.jinja = tg.render.render_jinja

class JinjaEngine(ew.TemplateEngine):

    @property
    def _environ(self):
        return config['pylons.app_globals'].jinja2_env

    def load(self, template_name):
        try:
            return self._environ.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise ew.errors.TemplateNotFound, '%s not found' % template_name

    def parse(self, template_text, filepath=None):
        return self._environ.from_string(template_text)

    def render(self, template, context):
        context = self.context(context)
        with ew.utils.push_context(ew.widget_context, render_context=context):
            text = template.render(**context)
            return literal(text)

class PackagePathLoader(jinja2.BaseLoader):

    def __init__(self):
        self.fs_loader = jinja2.FileSystemLoader(['/'])

    def get_source(self, environment, template):
        package, path = template.split(':')
        filename = pkg_resources.resource_filename(package, path)
        return self.fs_loader.get_source(environment, filename)


base_config = ForgeConfig()
