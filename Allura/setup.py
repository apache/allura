# -*- coding: utf-8 -*-
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

exec open('allura/version.py').read()

PROJECT_DESCRIPTION='''
Allura is an open source implementation of a software "forge", a web site
that manages source code repositories, bug reports, discussions, mailing
lists, wiki pages, blogs and more for any number of individual projects.
'''
setup(
    name='Allura',
    version=__version__,
    description='Base distribution of the Allura development platform',
    long_description=PROJECT_DESCRIPTION,
    author='SourceForge Team',
    author_email='develop@discussion.allura.p.re.sf.net',
    url='http://sourceforge.net/p/allura',
    keywords='sourceforge allura turbogears pylons jinja2 mongodb rabbitmq',
    license='Apache License, http://www.apache.org/licenses/LICENSE-2.0',
    platforms=[
        'Linux',
        'MacOS X',
        ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Pylons',
        'Framework :: TurboGears',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.6',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'License :: OSI Approved :: Apache Software License',
        ],
    install_requires=[
        "TurboGears2",
        "tg.devtools",
        "pypeline",
        "datadiff",
        "BeautifulSoup",
        "PasteScript",
        "Babel >= 0.9.4",
        "jinja2",
        "pysolr",
        "repoze.what-quickstart",
        "sqlalchemy-migrate",
        "Markdown >= 2.0.3",
        "Pygments >= 1.1.1",
        "PyYAML >= 3.09",
        "python-openid >= 2.2.4",
        "python-dateutil >= 1.4.1",
        "WebOb >= 0.9.8",
        "WebTest >= 1.2",
        "EasyWidgets >= 0.1.1",
        "PIL >= 1.1.7",
        "iso8601",
        "chardet >= 1.0.1",
        "feedparser >= 5.0.1",
        "oauth2 >= 1.2.0",
        "Ming >= 0.2.2dev-20110930",
        ],
    setup_requires=["PasteScript >= 1.7"],
    paster_plugins=['PasteScript', 'Pylons', 'TurboGears2', 'tg.devtools', 'Ming'],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    tests_require=['WebTest >= 1.2', 'BeautifulSoup', 'pytidylib', 'poster', 'nose'],
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

    [paste.paster_command]
    taskd = allura.command.taskd:TaskdCommand
    task = allura.command.taskd:TaskCommand
    models = allura.command:ShowModelsCommand
    reindex = allura.command:ReindexCommand
    ensure_index = allura.command:EnsureIndexCommand
    script = allura.command:ScriptCommand
    set-tool-access = allura.command:SetToolAccessCommand
    smtp_server=allura.command:SMTPServerCommand
    create-neighborhood = allura.command:CreateNeighborhoodCommand
    create-trove-categories = allura.command:CreateTroveCategoriesCommand
    set-neighborhood-level = allura.command:SetNeighborhoodLevel
    
    [easy_widgets.resources]
    ew_resources=allura.config.resources:register_ew_resources

    [easy_widgets.engines]
    jinja = allura.config.app_cfg:JinjaEngine

    """,
)

