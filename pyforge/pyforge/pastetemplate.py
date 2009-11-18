"""Definitions for TurboGears quickstart templates"""
from paste.script import templates
from tempita import paste_script_template_renderer

class ForgeAppTemplate(templates.Template):
    """
    PyForge app plugin paste template class
    """
    _template_dir = 'pastetemplates/forgeapp'
    template_renderer = staticmethod(paste_script_template_renderer)
    summary = 'PyForge Quickstart Template'
    egg_plugins = ['PasteScript', 'Pylons', 'TurboGears2', 'tg.devtools', 'pyforge']
    vars = [
        #templates.var('auth', 'use authentication and authorization support', default="sqlalchemy"),
        ]
