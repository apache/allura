# -*- coding: utf-8 -*-
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

from allura.version import __version__

requires = [ ]

setup(
    name='Allura',
    version=__version__,
    description='',
    author='SourceForge Team',
    author_email='allura@geek.net',
    url='http://sourceforge.net/p/',
    install_requires=requires,
    tests_require=requires + [ 'WebTest', 'BeautifulSoup', 'pytidylib', 'poster' ],
    paster_plugins=['PasteScript', 'Pyramid', 'Ming'],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    package_data={'allura': ['i18n/*/LC_MESSAGES/*.mo',
                                 'templates/*/*',
                                 'public/*/*']},
    message_extractors={'allura': [
            ('**.py', 'python', None),
            ('templates/**.mako', 'mako', None),
            ('templates/**.html', 'genshi', None),
            ('public/**', 'ignore', None)]},

    entry_points="""
    [paste.app_factory]
    main = allura.factory:main
    task = allura.factory:task
    tool_test = allura.factory:tool_test

    [paste.app_install]
    main = allura.websetup:Installer

    [allura]
    profile = allura.ext.user_profile:UserProfileApp
    admin = allura.ext.admin:AdminApp
    search = allura.ext.search:SearchApp
    home = allura.ext.project_home:ProjectHomeApp

    [allura.auth]
    local = allura.lib.plugin:LocalAuthenticationProvider
    ldap = allura.lib.plugin:LdapAuthenticationProvider

    [allura.user_prefs]
    local = allura.lib.plugin:LocalUserPreferencesProvider

    [allura.project_registration]
    local = allura.lib.plugin:LocalProjectRegistrationProvider

    [allura.theme]
    allura = allura.lib.plugin:ThemeProvider

    [flyway.migrations]
    pyforge = allura.migrations

    [paste.paster_command]
    taskd = allura.command.taskd:TaskdCommand
    task = allura.command.taskd:TaskCommand
    models = allura.command:ShowModelsCommand
    reindex = allura.command:ReindexCommand
    ensure_index = allura.command:EnsureIndexCommand
    script = allura.command:ScriptCommand
    set-tool-access = allura.command:SetToolAccessCommand
    smtp_server=allura.command:SMTPServerCommand
    
    [easy_widgets.resources]
    ew_resources=allura.config.resources:register_ew_resources

    [easy_widgets.engines]
    jinja = tg.render:JinjaEngine

    """,
)

