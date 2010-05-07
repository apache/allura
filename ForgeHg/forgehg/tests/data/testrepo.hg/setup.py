from setuptools import setup, find_packages
import sys, os

version = '0.2'

setup(name='EasyWidgets',
      version=version,
      description="A minimalistic approach to HTML generation and validation with TurboGears",
      long_description="""\
""",
      classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Framework :: TurboGears',
        'Framework :: TurboGears :: Widgets',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        'Topic :: Software Development :: Libraries :: Python Modules',
        ],
      keywords='TurboGears FormEncode TurboGears2',
      author='Rick Copeland',
      author_email='rick446@usa.net',
      url='blog.pythonisito.com',
      license='MIT',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      package_data={'ew': [
            'i18n/*/LC_MESSAGES/*.mo',
            'templates/*.html',
            'public/*/*']},
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
        'python-dateutil',
        'slimmer',
      ],
      entry_points="""
      # -*- Entry points: -*-
      [easy_widgets.resources]
      # dojo = ew.dojo:register_resources
      """,
      )
