
from helloforge.version import __version__

from setuptools import setup, find_packages

setup(name='HelloForge',
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
        'docutils',
      ],
      entry_points="""
      # -*- Entry points: -*-
      [allura]
      hello_forge=helloforge.main:HelloForgeApp
      """,
      )
