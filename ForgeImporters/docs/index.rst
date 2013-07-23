..     Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.

The *ForgeImporters* Package
============================

This package contains the base framework for project and
tool importers, as well as the core importers, for the
Allura platform.

Project importers will be available at
:file:`/{nbhd-prefix}/import_project/{importer-name}/`,
while individual tool importers will be available under the
Import sidebar entry on the project admin page.

Available Importers
===================

The following importers are available in this package for
use with an Allura system.

.. toctree::
   :maxdepth: 1
   :glob:

   importers/*

Importer Framework
==================

The following classes make up the base framework for
importers.

.. toctree::

   framework
