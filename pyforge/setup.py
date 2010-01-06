# -*- coding: utf-8 -*-
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

from pyforge.version import __version__

setup(
    name='pyforge',
    version=__version__,
    description='',
    author='',
    author_email='',
    #url='',
    install_requires=[
        "TurboGears2 >= 2.1a1",
        "PasteScript",
        "Babel >= 0.9.4",
        "Lamson",
        "Django",
        "Carrot",
        "Celery >= 0.8.0",
        "pymongo",
        "pysolr",
        "repoze.what-quickstart",
        "sqlalchemy-migrate",
        "Markdown >= 2.0.3",
        "Pygments >= 1.1.1",
        "PyYAML >= 3.09",
        "python-openid >= 2.2.4",
        "python-ldap == 2.3.9",
        "python-dateutil >= 1.4.1",
        ],
    setup_requires=["PasteScript >= 1.7"],
    paster_plugins=['PasteScript', 'Pylons', 'TurboGears2', 'tg.devtools'],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    tests_require=['WebTest', 'BeautifulSoup'],
    package_data={'pyforge': ['i18n/*/LC_MESSAGES/*.mo',
                                 'templates/*/*',
                                 'public/*/*']},
    message_extractors={'pyforge': [
            ('**.py', 'python', None),
            ('templates/**.mako', 'mako', None),
            ('templates/**.html', 'genshi', None),
            ('public/**', 'ignore', None)]},

    entry_points="""
    [paste.app_factory]
    main = pyforge.config.middleware:make_app
    plugin_test = pyforge.config.middleware:make_plugin_test_app

    [paste.app_install]
    main = pylons.util:PylonsInstaller
    plugin_test = pylons.util:PylonsInstaller

    [paste.paster_create_template]
    forgeapp=pyforge.pastetemplate:ForgeAppTemplate

    [pyforge]
    admin = pyforge.ext.admin:AdminApp
    search = pyforge.ext.search:SearchApp
    home = pyforge.ext.project_home:ProjectHomeApp

    [paste.paster_command]
    reactor_setup = pyforge.command:ReactorSetupCommand
    reactor = pyforge.command:ReactorCommand
    sendmsg = pyforge.command:SendMessageCommand
    
    """,
)

