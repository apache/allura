from setuptools import setup, find_packages
import sys, os

from sfx.version import __version__

setup(
    name='ForgeClassic',
    version=__version__,
    description="",
    long_description="""\
""",
    classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    keywords='',
    author='',
    author_email='',
    url='',
    license='',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        # -*- Extra requirements: -*-
        'Allura',
        'sqlalchemy==0.6beta3',
        'psycopg2==2.2.2',
        'mysql-python==1.2.3c1',
        ],
    entry_points="""
    # -*- Entry points: -*-
    [allura]
    sfx = sfx:SFXApp
    mailman = sfx:MailmanApp
    vhost = sfx:VHostApp
    mysql = sfx:MySQLApp
    hosted_apps = sfx:HostedAppsApp

    [allura.auth]
    sfx = sfx:SFXAuthenticationProvider

    [allura.project_registration]
    sfx = sfx:SFXProjectRegistrationProvider

    """,
      )
