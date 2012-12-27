from setuptools import setup, find_packages
import sys, os

from bitergiametrics.version import __version__

setup(name='BitergiaMetrics',
      version=__version__,
      description="",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='Alvaro del Castillo, Bitergia',
      author_email='acs@bitergia.com',
      url='',
      license='Apache License Version 2.0',
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
      metrics=bitergiametrics.main:BitergiaMetricsApp
      """,
      )
