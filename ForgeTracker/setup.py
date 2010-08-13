from setuptools import setup, find_packages
import sys, os

from forgetracker.version import __version__

setup(name='ForgeTracker',
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
          'tw.forms',
      ],
      entry_points="""
      # -*- Entry points: -*-
      [allura]
      Tickets=forgetracker.tracker_main:ForgeTrackerApp

      [flyway.migrations]
      ForgeTracker=forgetracker.model.migrations

      [easy_widgets.resources]
      ew_resources=forgetracker.config.resources:register_ew_resources
      """,
      )
