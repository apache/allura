#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from setuptools import setup, find_packages


setup(name='ForgeImporters',
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
      [allura.project_importers]
      trac = forgeimporters.trac.project:TracProjectImporter
      github = forgeimporters.github.project:GitHubProjectImporter

      [allura.importers]
      github-tracker = forgeimporters.github.tracker:GitHubTrackerImporter
      github-wiki = forgeimporters.github.wiki:GitHubWikiImporter
      github-repo = forgeimporters.github.code:GitHubRepoImporter
      trac-tickets = forgeimporters.trac.tickets:TracTicketImporter
      forge-tracker = forgeimporters.forge.tracker:ForgeTrackerImporter
      forge-discussion = forgeimporters.forge.discussion:ForgeDiscussionImporter

      [allura.admin]
      importers = forgeimporters.base:ImportAdminExtension
      """,)
