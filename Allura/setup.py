# -*- coding: utf-8 -*-
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

from allura.version import __version__

setup(
    name='Allura',
    version=__version__,
    description='',
    author='SourceForge Team',
    author_email='allura@geek.net',
    url='http://sourceforge.net/p/',
    install_requires=[
        "TurboGears2 >= 2.1a1",
        "PasteScript",
        "Babel >= 0.9.4",
        "pymongo >= 1.7",
        "pysolr",
        "repoze.what-quickstart",
        "sqlalchemy-migrate",
        "Markdown >= 2.0.3",
        "Pygments >= 1.1.1",
        "PyYAML >= 3.09",
        "python-openid >= 2.2.4",
        "python-ldap == 2.3.9",
        "python-dateutil >= 1.4.1",
        "WebOb == 0.9.8",
        "WebTest == 1.2",
        "python-oembed >= 0.1.1",
        "EasyWidgets >= 0.1.1",
        "PIL >= 1.1.7",
        "iso8601",
        "chardet == 1.0.1",
        "feedparser >= 5.0.1",
        "oauth2 == 1.2.0",
        ],
    setup_requires=["PasteScript >= 1.7"],
    paster_plugins=['PasteScript', 'Pylons', 'TurboGears2', 'tg.devtools', 'Ming'],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    tests_require=['WebTest >= 1.2', 'BeautifulSoup', 'pytidylib', 'poster'],
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
    main = allura.config.middleware:make_app
    task = allura.config.middleware:make_task_app
    tool_test = allura.config.middleware:make_tool_test_app

    [paste.app_install]
    main = pylons.util:PylonsInstaller
    tool_test = pylons.util:PylonsInstaller

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
    jinja = allura.config.app_cfg:JinjaEngine

    """,
)

