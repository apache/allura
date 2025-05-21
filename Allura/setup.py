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

from setuptools import setup
__version__ = "undefined"
exec(open('allura/version.py').read())  # noqa: S102

PROJECT_DESCRIPTION = '''
Allura is an open source implementation of a software "forge", a web site
that manages source code repositories, bug reports, discussions, mailing
lists, wiki pages, blogs and more for any number of individual projects.
'''
setup(
    name='Allura',
    version=__version__,
)
