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

Extending Allura with Entry Points
===================================

There are many extension points to extending Allura.  They all make themselves
known to Allura via python entry points defined in ``setup.py``.  Many are then
available immediately.  Others, such as authentication providers or themes, need
to be specified in your ``.ini`` file, since you may only have one enabled at a time.

The available extension points for Allura are:

* :class:`allura.app.Application` (aka tool) and :class:`allura.app.Artifact`
* :class:`allura.lib.plugin.ThemeProvider`
* :class:`allura.lib.plugin.ProjectRegistrationProvider`
* :class:`allura.lib.plugin.AuthenticationProvider`
* :class:`allura.lib.plugin.UserPreferencesProvider`
* :class:`allura.lib.plugin.AdminExtension`
* :class:`allura.lib.spam.SpamFilter`
* ``site_stats`` in the root API data.  Docs in :class:`allura.controllers.rest.RestController`
* :mod:`allura.lib.package_path_loader` (for overriding templates)
* ``[allura.timers]`` functions which return a list or single :class:`timermiddleware.Timer` which will be included in stats.log timings

A listing of available 3rd-party extensions is at https://forge-allura.apache.org/p/allura/wiki/Extensions/

To disable any Allura entry point, simply add an entry in your ``.ini`` config file
with names and values corresponding to entry points defined in any ``setup.py`` file.
For example if you have ForgeImporter set up, but want to disable the google code importers:

.. code-block:: ini

    disable_entry_points.allura.project_importers = google-code
    disable_entry_points.allura.importers = google-code-tracker, google-code-repo

Other entry points are used to provide ``paster`` commands and ``easy_widget`` configuration,
which are not part of Allura but are used by Allura.


Event Handlers
==============

Another way to extend Allura is set up event handlers to respond to Allura events.
There is documentation and examples at :ref:`events`.

The events that allura publishes are:

* project_created
* project_updated
* repo_cloned
* repo_refreshed
* repo_clone_task_failed
