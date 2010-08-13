from setuptools import setup, find_packages
import sys, os

from forgewiki.version import __version__

setup(name='ForgeWiki',
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
          'allura',
      ],
      entry_points="""
      # -*- Entry points: -*-
      [allura]
      Wiki=forgewiki.wiki_main:ForgeWikiApp

      [flyway.migrations]
      ForgeWiki=forgewiki.model.migrations
      """,
      )
