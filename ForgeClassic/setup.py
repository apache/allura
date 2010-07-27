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
        'pyforge',
        ],
    entry_points="""
    # -*- Entry points: -*-
    [pyforge]
    sfx = sfx:SFXApp
    mailman = sfx:MailmanApp

    [pyforge.auth]
    sfx = sfx:SFXAuthenticationProvider

    [pyforge.project_registration]
    sfx = sfx:SFXProjectRegistrationProvider
    """,
      )
