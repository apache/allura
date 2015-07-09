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

************
Using Allura
************


We don't have much end-user help for Allura yet.  SourceForge projects use Allura,
though, so their support documentation may be useful to anyone using Allura:

.. _what-are-neighborhoods:

What are neighborhoods?
-----------------------

You can think of neighborhoods as groups of logically related projects, which all have the same default options. Allura has two default neighborhoods: "Projects" and "Users". The "Users" neighborhood is special, it contains a project for every user registered on a site. This user projects contain a few special tools, e.g. "Profile" and "Statistics".   The "Projects" contains all other projects.

Each neighborhood has admin interface. You can get there by clicking "Neighborhood administration" from the home page of the neighborhood or by "Admin" icon in the top toolbar.

This interface allows you to:

- add a new project to the neighborhood
- change neighborhood's name
- change neighborhood icon
- configure redirect from neighborhood's main page to other url
- specify :ref:`project template <project-templates>` for newly created projects
- specify project list url (the link will be displayed under neighborhood name in page header)
- :ref:`anchor tools <anchored-tools>` in the top menu for each project in the neighborhood
- :ref:`prohibit installation of specific tools <prohibited-tools>` in all projects of this neighborhood

.. _project-templates:

Project Templates
^^^^^^^^^^^^^^^^^

TODO

.. _anchored-tools:

Anchored Tools
^^^^^^^^^^^^^^

TODO

.. _prohibited-tools:

Prohibited Tools
^^^^^^^^^^^^^^^^

TODO


Configuring your project
------------------------

See SourceForge help page: https://sourceforge.net/p/forge/documentation/Create%20a%20New%20Project/

Note there are some SourceForge-specific references that don't apply to other Allura instances.


Using tickets
-------------

See SourceForge help page: https://sourceforge.net/p/forge/documentation/Tickets/


Using the wiki
--------------

See SourceForge help page: https://sourceforge.net/p/forge/documentation/Wiki/


Using a discussion forum
------------------------

See SourceForge help page: https://sourceforge.net/p/forge/documentation/Discussion/


Adding an external link
-----------------------

See SourceForge help page: https://sourceforge.net/p/forge/documentation/External%20Link/


Using markdown syntax
---------------------

Everything in Allura uses Markdown formatting, with several customizations and macros
specifically for Allura.  There are "Formatting Help" buttons throughout Allura for
easy reference to the Markdown syntax.  One such page is https://forge-allura.apache.org/p/allura/wiki/markdown_syntax/
