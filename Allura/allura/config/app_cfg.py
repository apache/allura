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
import sys

import tg
from tg.configuration import config
from tg.configurator.application import ApplicationConfigurator
from tg.configurator.components.mimetypes import MimeTypesConfigurationComponent
from tg.configurator.components.paths import PathsConfigurationComponent
from tg.configurator.components.app_globals import AppGlobalsConfigurationComponent
from tg.configurator.components.helpers import HelpersConfigurationComponent
from tg.configurator.components.dispatch import DispatchConfigurationComponent
from tg.configurator.components.rendering import TemplateRenderingConfigurationComponent
from tg.renderers.jinja import JinjaRenderer
from tg.renderers.json import JSONRenderer

import jinja2
from markupsafe import Markup
import ew
from tg.support.converters import asint

import allura
# needed for tg.configuration to work
from allura.lib import app_globals, helpers
from allura.lib.package_path_loader import PackagePathLoader

log = logging.getLogger(__name__)


class MinimalApplicationConfiguratorNoRegistry(ApplicationConfigurator):
    """
    Copied from tg.MinimalApplicationConfigurator but without the registry
    since we use RegistryManager in a specific part of our middleware already
    """
    def __init__(self):
        super().__init__()
        self.register(MimeTypesConfigurationComponent, after=False)
        self.register(PathsConfigurationComponent, after=False)
        self.register(DispatchConfigurationComponent, after=False)
        self.register(AppGlobalsConfigurationComponent)
        self.register(HelpersConfigurationComponent)
        self.register(TemplateRenderingConfigurationComponent)
        # self.register(RegistryConfigurationComponent, after=True)


class ForgeConfig(MinimalApplicationConfiguratorNoRegistry):

    def __init__(self, root_controller=None):
        super().__init__()

        self.update_blueprint({
            'package': allura,
            'root_controller': root_controller,  # optional override, otherwise default will be found in allura package
            'renderers': ['json', 'jinja'],
            'default_renderer': 'jinja',

            # prevent dispatcher from striping extensions like '.io' from URLs
            'disable_request_extensions': True,

            # if left to True (default) would use crank.util.default_path_translator to convert all URL punctuation to "_"
            # which is convenient for /foo-bar to execute a "def foo_bar" method, but is a pretty drastic change for us
            # and makes many URLs be valid that we might not want like /foo*bar /foo@bar /foo:bar
            'dispatch_path_translator': None,

        })
        self.replace(TemplateRenderingConfigurationComponent.id, AlluraTemplateConfig)


class AlluraTemplateConfig(TemplateRenderingConfigurationComponent):

    def on_bind(self, configurator: ForgeConfig):
        # no super, only register a few (other ones aren't a problem but are unnecessary, so this is optimal)
        self.register_engine(JSONRenderer)
        # this is *our* JinjaRenderer, not the default one
        self.register_engine(AlluraJinjaRenderer)


class AlluraJinjaRenderer(JinjaRenderer):

    @classmethod
    def _setup_bytecode_cache(cls):
        cache_type = config.get('jinja_bytecode_cache_type')
        bcc = None
        try:
            if cache_type == 'memcached' and config.get('memcached_host'):
                import pylibmc
                from jinja2 import MemcachedBytecodeCache
                client = pylibmc.Client([config['memcached_host']])
                bcc_prefix = f'jinja2/{jinja2.__version__}/'
                bcc_prefix += f'py{sys.version_info.major}{sys.version_info.minor}/'
                bcc = MemcachedBytecodeCache(client, prefix=bcc_prefix)
            elif cache_type == 'filesystem':
                from jinja2 import FileSystemBytecodeCache
                bcc = FileSystemBytecodeCache(pattern=f'__jinja2_{jinja2.__version__}_%s.cache')
        except Exception:
            log.exception("Error encountered while setting up a" +
                          " %s-backed bytecode cache for Jinja" % cache_type)
        return bcc

    @classmethod
    def create(cls, config, app_globals):
        # this has evolved over the age of allura, and upgrades of TG
        # the parent JinjaRenderer logic is different, some may be better and hasn't been incorporated into ours yet

        bcc = cls._setup_bytecode_cache()
        jinja2_env = jinja2.Environment(
            loader=PackagePathLoader(),
            auto_reload=config['auto_reload_templates'],
            autoescape=True,
            bytecode_cache=bcc,
            cache_size=asint(config.get('jinja_cache_size', -1)),
            extensions=['jinja2.ext.do', 'jinja2.ext.i18n'])
        jinja2_env.install_gettext_translations(tg.i18n)
        jinja2_env.filters['datetimeformat'] = helpers.datetimeformat
        jinja2_env.filters['filter'] = lambda s, t=None: list(filter(t and jinja2_env.tests[t], s))
        jinja2_env.filters['nl2br'] = helpers.nl2br_jinja_filter
        jinja2_env.filters['subrender'] = helpers.subrender_jinja_filter
        jinja2_env.globals.update({
            'hasattr': hasattr,
            'h': helpers,
            'g': app_globals,
            'c': tg.tmpl_context,
            'request': tg.request,
        })
        config['tg.app_globals'].jinja2_env = jinja2_env  # TG doesn't need this, but we use g.jinja2_env a lot
        return {'jinja': cls(jinja2_env)}


class JinjaEngine(ew.TemplateEngine):

    @property
    def _environ(self):
        return config['tg.app_globals'].jinja2_env

    def load(self, template_name):
        try:
            return self._environ.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise ew.errors.TemplateNotFound('%s not found' % template_name)

    def parse(self, template_text, filepath=None):
        return self._environ.from_string(template_text)

    def render(self, template, context):
        context = self.context(context)
        with ew.utils.push_context(ew.widget_context, render_context=context):
            text = template.render(**context)
            return Markup(text)


base_config = ForgeConfig()
