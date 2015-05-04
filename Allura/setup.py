# -*- coding: utf-8 -*-

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

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

exec open('allura/version.py').read()

PROJECT_DESCRIPTION = '''
Allura is an open source implementation of a software "forge", a web site
that manages source code repositories, bug reports, discussions, mailing
lists, wiki pages, blogs and more for any number of individual projects.
'''
setup(
    name='Allura',
    version=__version__,
    description='Base distribution of the Allura development platform',
    long_description=PROJECT_DESCRIPTION,
    author='Allura Team',
    url='https://allura.apache.org/',
    keywords='allura forge turbogears pylons jinja2 mongodb',
    license='Apache License, http://www.apache.org/licenses/LICENSE-2.0',
    platforms=[
        'Linux',
        'MacOS X',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Pylons',
        'Framework :: TurboGears',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.6',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'License :: OSI Approved :: Apache Software License',
    ],
    install_requires=[
        "TurboGears2",
        "pypeline",
        "datadiff",
        "BeautifulSoup",
        "PasteScript",
        "Babel >= 0.9.4",
        "jinja2",
        "pysolr",
        "Markdown >= 2.0.3",
        "Pygments >= 1.1.1",
        "EasyWidgets >= 0.1.1",
        "iso8601",
        "chardet >= 1.0.1",
        "feedparser >= 5.0.1",
        "oauth2 >= 1.2.0",
        "Ming >= 0.2.2dev-20110930",
    ],
    setup_requires=["PasteScript >= 1.7"],
    paster_plugins=['PasteScript', 'Pylons', 'TurboGears2', 'Ming'],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    tests_require=['WebTest >= 1.2', 'BeautifulSoup', 'poster', 'nose'],
    package_data={'allura': ['i18n/*/LC_MESSAGES/*.mo',
                             'templates/**.html',
                             'templates/**.py',
                             'templates/**.xml',
                             'templates/**.txt',
                             'public/*/*/*/*/*',
                             ]},
    message_extractors={'allura': [
        ('**.py', 'python', None),
        ('templates/**.html', 'genshi', None),
        ('public/**', 'ignore', None)]},

    # These entry points define what tools and plugins are available for Allura.
    # Other packages (the Forge* directories) or 3rd-party can add more too.
    # development.ini is used for many cases to specify which to actually use.
    entry_points="""
    [paste.app_factory]
    main = allura.config.middleware:make_app
    [paste.app_install]
    main = pylons.util:PylonsInstaller

    [allura]
    profile = allura.ext.user_profile:UserProfileApp
    admin = allura.ext.admin:AdminApp
    search = allura.ext.search:SearchApp
    home = allura.ext.project_home:ProjectHomeApp

    [allura.auth]
    local = allura.lib.plugin:LocalAuthenticationProvider
    ldap = allura.lib.plugin:LdapAuthenticationProvider

    [allura.user_prefs]
    local = allura.lib.plugin:LocalUserPreferencesProvider
    ldap = allura.lib.plugin:LdapUserPreferencesProvider

    [allura.project_registration]
    local = allura.lib.plugin:LocalProjectRegistrationProvider

    [allura.theme]
    allura = allura.lib.plugin:ThemeProvider

    [allura.spam]
    akismet = allura.lib.spam.akismetfilter:AkismetSpamFilter
    mollom = allura.lib.spam.mollomfilter:MollomSpamFilter

    [allura.phone]
    nexmo = allura.lib.phone.nexmo:NexmoPhoneService

    [allura.site_admin]
    stats = allura.controllers.site_admin:StatsSiteAdminExtension
    troves = allura.controllers.trovecategories:TroveCategorySiteAdminExtension

    [allura.user_profile.sections]
    personal-data = allura.ext.user_profile.user_main:PersonalDataSection
    projects = allura.ext.user_profile.user_main:ProjectsSection
    skills = allura.ext.user_profile.user_main:SkillsSection
    tools = allura.ext.user_profile.user_main:ToolsSection
    social = allura.ext.user_profile.user_main:SocialSection

    [allura.webhooks]
    repo-push = allura.webhooks:RepoPushWebhookSender

    [paste.paster_command]
    taskd = allura.command.taskd:TaskdCommand
    taskd_cleanup = allura.command.taskd_cleanup:TaskdCleanupCommand
    task = allura.command.taskd:TaskCommand
    models = allura.command:ShowModelsCommand
    reindex = allura.command:ReindexCommand
    ensure_index = allura.command:EnsureIndexCommand
    script = allura.command:ScriptCommand
    set-tool-access = allura.command:SetToolAccessCommand
    smtp_server=allura.command:SMTPServerCommand
    create-neighborhood = allura.command:CreateNeighborhoodCommand
    update-neighborhood-home-tool = allura.command:UpdateNeighborhoodCommand
    create-trove-categories = allura.command:CreateTroveCategoriesCommand
    set-neighborhood-features = allura.command:SetNeighborhoodFeaturesCommand
    reclone-repo = allura.command.reclone_repo:RecloneRepoCommand

    [easy_widgets.resources]
    ew_resources=allura.config.resources:register_ew_resources

    [easy_widgets.engines]
    jinja = allura.config.app_cfg:JinjaEngine

    [activitystream]
    storage = activitystream.storage.mingstorage:MingStorage
    director = allura.model.timeline:Director
    aggregator = allura.model.timeline:Aggregator
    """,
)
