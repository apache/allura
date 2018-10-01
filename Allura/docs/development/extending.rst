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

*********
Extending
*********

Extension APIs and Entry Points
===============================

There are many extension points to extending Allura.  They all make themselves
known to Allura via python entry points defined in ``setup.py``.  Many are then
available immediately.  Others, such as authentication providers or themes, need
to be specified in your ``.ini`` file, since you may only have one enabled at a time.

The available extension points for Allura are:

* :class:`allura.app.Application` (aka tool) and :class:`allura.model.artifact.Artifact`
* :class:`allura.lib.plugin.ThemeProvider`
* :class:`allura.lib.plugin.ProjectRegistrationProvider`
* :class:`allura.lib.plugin.AuthenticationProvider`
* :class:`allura.lib.multifactor.TotpService`
* :class:`allura.lib.plugin.UserPreferencesProvider`
* :class:`allura.lib.plugin.AdminExtension`
* :class:`allura.lib.plugin.SiteAdminExtension`
* :class:`allura.lib.spam.SpamFilter`
* :class:`allura.lib.phone.PhoneService`
* ``site_stats`` in the root API data.  Docs in :class:`allura.controllers.rest.RestController`
* :mod:`allura.lib.package_path_loader` (for overriding templates)
* ``[allura.timers]`` functions which return a list or single :class:`timermiddleware.Timer` which will be included in stats.log timings
* :mod:`allura.ext.user_profile.user_main`
* :mod:`allura.ext.personal_dashboard.dashboard_main`
* ``[allura.middleware]`` classes, which are standard WSGI middleware.  They will receive the ``app`` instance and a ``config`` dict as constructor parameters.
  The middleware will be used for all requests.  By default the middleware wraps the base app directly and other middleware wrap around it.
  If your middleware needs to wrap around the other Allura middleware (except error handling), set ``when = 'outer'`` on your middleware.
* :class:`allura.webhooks.WebhookSender`

A listing of available 3rd-party extensions is at https://forge-allura.apache.org/p/allura/wiki/Extensions/

To disable any Allura entry point, simply add an entry in your ``.ini`` config file
with names and values corresponding to entry points defined in any ``setup.py`` file.
For example if you have ForgeImporter set up, but want to disable the GitHub importers:

.. code-block:: ini

    disable_entry_points.allura.project_importers = github
    disable_entry_points.allura.importers = github-tracker, github-wiki, github-repo

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
* trove_category_created
* trove_category_updated
* trove_category_deleted


Markdown Macros
===============

Most text inputs in Allura accept Markdown text which is parsed and turned into
HTML before being rendered. The Markdown text may contain "macros" - custom
commands which extend the Markdown language. Here's an example of a macro
that comes with Allura::

    [[project_admins]]

Include this macro in a wiki page or other Markdown content, and when rendered
it will be replaced by an actual list of the project's admin users.

Extending Allura with your own macros is simple, requiring two basic steps:

1. Decide on a name for your macro, then create a function with that name, and
   decorate it with the `macro()` decorator from Allura. The function can
   accept keyword arguments, and must return text or HTML. For example::

    from allura.lib.macro import macro

    @macro()
    def hello(name='World'):
        return "<p>Hello {}!</p>".format(name)

2. Add an entry point for your macro to the `setup.py` for your package::

    [allura.macros]
    hello_macro = mypkg.mymodule:hello

Note that the key name (`hello_macro` in this case) doesn't matter - the macro
is named after the function name. Our example macro could be used in a couple
ways::

    [[hello]]
    [[hello name=Universe]]

For more help with macros, consult the source code for the macros that ship
with Allura. You can find them in the `allura.lib.macro` package.
