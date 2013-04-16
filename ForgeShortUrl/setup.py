from setuptools import setup, find_packages


setup(name='ForgeShortUrl',
      description="",
      long_description="",
      classifiers=[],
      keywords='',
      author='',
      author_email='',
      url='',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=['Allura', ],
      entry_points="""
      # -*- Entry points: -*-
      [allura]
      ShortURL=forgeshorturl.main:ForgeShortUrlApp

      """,)
