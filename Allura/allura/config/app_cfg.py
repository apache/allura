# -*- coding: utf-8 -*-

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
from functools import partial

import tg
import jinja2
import pylons
from tg.configuration import AppConfig, config
from routes import Mapper
from webhelpers.html import literal

import ew

import allura
# needed for tg.configuration to work
from allura.lib import app_globals, helpers
from allura.lib.package_path_loader import PackagePathLoader

log = logging.getLogger(__name__)


class ForgeConfig(AppConfig):

    def __init__(self, root_controller='root'):
        AppConfig.__init__(self)
        self.root_controller = root_controller
        self.package = allura
        self.renderers = ['json', 'genshi', 'mako', 'jinja']
        self.default_renderer = 'genshi'
        self.use_sqlalchemy = False
        self.use_toscawidgets = True
        self.use_transaction_manager = False
        self.handle_status_codes = [403, 404]
        self.disable_request_extensions = True

    def after_init_config(self):
        config['pylons.strict_c'] = True

    def setup_routes(self):
        map = Mapper()
        # Setup a default route for the root of object dispatch
        map.connect('*url', controller=self.root_controller,
                    action='routes_placeholder')
        config['routes.map'] = map

    def _setup_bytecode_cache(self):
        cache_type = config.get('jinja_bytecode_cache_type')
        bcc = None
        try:
            if cache_type == 'memcached' and config.get('memcached_host'):
                import pylibmc
                from jinja2 import MemcachedBytecodeCache
                client = pylibmc.Client([config['memcached_host']])
                bcc = MemcachedBytecodeCache(client)
            elif cache_type == 'filesystem':
                from jinja2 import FileSystemBytecodeCache
                bcc = FileSystemBytecodeCache()
        except:
            log.exception("Error encountered while setting up a" +
                          " %s-backed bytecode cache for Jinja" % cache_type)
        return bcc

    def setup_jinja_renderer(self):
        bcc = self._setup_bytecode_cache()
        jinja2_env = jinja2.Environment(
            loader=PackagePathLoader(),
            auto_reload=config.auto_reload_templates,
            autoescape=True,
            bytecode_cache=bcc,
            cache_size=config.get('jinja_cache_size', -1),
            extensions=['jinja2.ext.do', 'jinja2.ext.i18n'])
        jinja2_env.install_gettext_translations(pylons.i18n)
        jinja2_env.filters['filesizeformat'] = helpers.do_filesizeformat
        jinja2_env.filters['datetimeformat'] = helpers.datetimeformat
        jinja2_env.filters['filter'] = lambda s,t=None: filter(t and jinja2_env.tests[t], s)
        jinja2_env.filters['nl2br'] = helpers.nl2br_jinja_filter
        jinja2_env.globals.update({'hasattr': hasattr})
        config['pylons.app_globals'].jinja2_env = jinja2_env
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

base_config = ForgeConfig()
