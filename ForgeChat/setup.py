from setuptools import setup, find_packages
import sys, os

from forgechat.version import __version__

setup(name='ForgeChat',
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
      Chat=forgechat.main:ForgeChatApp

      [paste.global_paster_command]
      ircbot=forgechat.command:IRCBotCommand
      """,
      )
