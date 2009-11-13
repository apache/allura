from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='Ming',
      version=version,
      description="Bringing order to Mongo since 2009",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='mongo, pymongo',
      author='Rick Copeland',
      author_email='rick@geek.net',
      url='',
      license='Apache',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          # -*- Extra requirements: -*-
        "mock >= 0.6.0",
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
