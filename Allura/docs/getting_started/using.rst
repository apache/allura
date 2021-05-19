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

.. contents::
   :local:


.. _what-are-neighborhoods:

What are neighborhoods?
-----------------------

You can think of neighborhoods as groups of logically related projects, which all have the same default options. Allura has two default neighborhoods: "Projects" and "Users". The "Users" neighborhood is special, it contains a project for every user registered on a site. These user projects contain a few special tools, e.g. "Profile" and "Statistics".   The "Projects" neighborhood contains all other projects.

Each neighborhood has an admin interface. You can get there by clicking "Neighborhood administration" from the home page of the neighborhood or by "Admin" icon in the top toolbar.

This interface allows you to:

- add a new project to the neighborhood
- change the neighborhood's name
- change the neighborhood's icon
- configure redirect from neighborhood's main page to other url
- specify a :ref:`project template <project-templates>` for newly created projects
- specify a project list url (the link will be displayed under neighborhood name in page header)
- :ref:`anchor tools <anchored-tools>` in the top menu for each project in the neighborhood
- :ref:`prohibit installation of specific tools <prohibited-tools>` in all projects of this neighborhood

.. _project-templates:

Project Templates
^^^^^^^^^^^^^^^^^

Allows you to specify a template for newly created projects. The template controls default tools, permissions, labels, etc for a project.  If a template is specified, it is used during project creation and no tool choices are possible.  It is formatted as JSON dictionary with the following structure:

.. code-block:: javascript

  {
    "private": false,
    "tools": {
        "tool_name": {               /* e.g. wiki, git, tickets, etc */
          "label": "Tool Label",     /* Required */
          "mount_point": "url-path"  /* Required */
          "options": {}              /* Any other tool's options here. Optional */
        }
    },
    "groups": [
      {
        "name": "Admin",        /* Default groups are: Admin, Developer, Member */
        "usernames": ["admin1"] /* Add existing users to existing group */
      },
      {
        "name": "New Group",     /* You can also create a new group */
        "usernames": ["user1"],  /* and add existing users to it */
        /*
         * Then you need to specify permissions for newly created group.
         * Supported permissions are: admin, create, update, read
         */
        "permissions": ["read", "update"]
      }
    ],
    "tool_order": ["wiki", "tickets", "git"], /* tools order in the topbar menu */
    "labels": ["Open Source", "web"],
    "trove_cats": {
      /*
       * Available trove types are: root_database, license, developmentstatus,
       * audience, os, language, topic, natlanguage, environment.
       */
      "trove_type": [905, 869]  /* TroveCategory ids */
    },
    "icon": {
      "url: "http://img.host/path/to/image.png",  /* Required */
      "filename": "default-project-icon.png"      /* Required */
    }
  }

Top level keys are optional.

.. _anchored-tools:

Anchored Tools
^^^^^^^^^^^^^^

Anchored tools allow you to "anchor" specific tools at the beginning of the topbar menu for all projects belonging to the neighborhood.  If the specified tool does not exist in the project, it will be created automatically.  These tools can not be removed by the project.

To configure them, go to "Neighborhood Admin -> Overview".  Use the following
format "tool_name:The Label, another_tool:Another Label", e.g.

.. code-block:: text

    wiki:Wiki, activity:Activity


.. _prohibited-tools:

Prohibited Tools
^^^^^^^^^^^^^^^^

Prohibited tools allow you to forbid installation of specific tools for all the projects belonging to the neighborhood. Tools already installed in the project will not be automatically removed. To configure prohibited tools , just list tool names using comma as separator. E.g.

.. code-block:: text

  blog, discussion, svn


Configuring your project
------------------------

We don't have much end-user help for Allura yet.  SourceForge projects use Allura,
though, so their support documentation may be useful to anyone using Allura:

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
easy reference to the Markdown syntax.  One such page is https://forge-allura.apache.org/nf/markdown_syntax
