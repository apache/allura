# -*- coding: utf-8 -*-
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

setup(
    name='pyforge',
    version='0',
    description='',
    author='',
    author_email='',
    #url='',
    install_requires=[
        ],
    entry_points="""
    [paste.app_factory]

    [paste.app_install]

    [paste.paster_create_template]

    [allura]

    [allura.auth]

    [allura.project_registration]

    [flyway.migrations]

    [flyway.test_migrations]

    [paste.paster_command]
    
    [easy_widgets.resources]

    """,
)

