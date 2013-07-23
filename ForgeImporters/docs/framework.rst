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

:mod:`forgeimporters.base`
==========================

The following classes make up the base framework for
importers.

These can be used to create additional importers
for Allura, which can be made available by creating an
appropriate entry-point under `allura.project_importers` or
`allura.importers` for project importers or tool importers,
respectively.

:class:`~forgeimporters.base.ProjectImporter`
---------------------------------------------

.. autoclass:: forgeimporters.base.ProjectImporter
   :members:

:class:`~forgeimporters.base.ToolImporter`
------------------------------------------

.. autoclass:: forgeimporters.base.ToolImporter
   :members:

:class:`~forgeimporters.base.ToolsValidator`
--------------------------------------------

.. autoclass:: forgeimporters.base.ToolsValidator
   :members:
