from setuptools import setup, find_packages
import sys, os

from forgegit.version import __version__

setup(name='ForgeGit',
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
      Git=forgegit.git_main:ForgeGitApp
      """,
      )
