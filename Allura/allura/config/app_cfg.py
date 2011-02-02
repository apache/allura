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

from tg.configuration import AppConfig, config
from paste.deploy.converters import asbool
from routes import Mapper
from webhelpers.html import literal

import ew

import allura
import allura.lib.helpers as h
from allura.lib import app_globals, custom_middleware


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

    def add_error_middleware(self, global_conf, app):
        app = AppConfig.add_error_middleware(self, global_conf, app)
        app = custom_middleware.LoginRedirectMiddleware(app)
        return app

    def after_init_config(self):
        config['pylons.strict_c'] = True

    def add_core_middleware(self, app):
        if asbool(config.get('auth.method', 'local')=='sfx'):
            import sfx.middleware
            d = h.config_with_prefix(config, 'auth.')
            d.update(h.config_with_prefix(config, 'sfx.'))
            app = sfx.middleware.SfxMiddleware(app, d)
        return super(ForgeConfig, self).add_core_middleware(app)

    def setup_routes(self):
        map = Mapper(directory=config['pylons.paths']['controllers'],
                     always_scan=config['debug'])
        # Setup a default route for the root of object dispatch
        map.connect('*url', controller=self.root_controller,
                    action='routes_placeholder')
        config['routes.map'] = map

    def setup_jinja_renderer(self):
        from jinja2 import ChoiceLoader, Environment, PackageLoader
        from tg.render import render_jinja

        loaders = {'allura': PackageLoader('allura', 'templates')}
        for ep in pkg_resources.iter_entry_points('allura'):
            if not ep.module_name in loaders:
                log.info('Registering templates for application %s', ep.module_name)
                try:
                    loaders[ep.module_name] = PackageLoader(ep.module_name, 'templates')
                except ImportError:
                    log.warning('Cannot import entry point %s', ep)
                    continue

        config['pylons.app_globals'].jinja2_env = Environment(
            loader=ChoiceLoader(loaders.values()),
            auto_reload=self.auto_reload_templates,
            autoescape=True,
            extensions=['jinja2.ext.do'])
        # Jinja's unable to request c's attributes without strict_c
        config['pylons.strict_c'] = True

        self.render_functions.jinja = render_jinja

class JinjaEngine(ew.TemplateEngine):

    def __init__(self, entry_point, config):
        import jinja2
        self.jinja2 = jinja2
        super(JinjaEngine, self).__init__(entry_point, config)

    @property
    def _environ(self):
        return config['pylons.app_globals'].jinja2_env

    def load(self, template_name):
        try:
            return self._environ.get_template(template_name)
        except self.jinja2.TemplateNotFound:
            raise ew.errors.TemplateNotFound, '%s not found' % template_name

    def parse(self, template_text, filepath=None):
        return self._environ.from_string(template_text)

    def render(self, template, context):
        context = self.context(context)
        with ew.utils.push_context(ew.widget_context, render_context=context):
            text = template.render(**context)
            return literal(text)

base_config = ForgeConfig()
