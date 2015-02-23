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

***********
Permissions
***********

Guide to Users, Groups and Permissions in Allura
================================================

User/Group model
----------------

In the allura system `users` can be assigned to various `groups` or
roles on a per-project basis.

Users can be members of many groups, and `groups` can
be assigned a list of `permissions` like `edit`,
`mdoderate` or `read`.   Tools can define their own
set of permissions, for their artifacts.

Individual artifacts and ACL's
------------------------------

You may want to assign a permission
to particular people or roles for a specific `Artifact` such as
one bug in the ticket tracker.  The Allura platform supports this via
an additive ACL field on every `Artifact` instance.  It is not exposed
via the UI currently.

Permission hierarchy
--------------------

Projects and subprojects can define user groups, but for any particular
subproject the set of groups the user belongs to is additive.  This follows
the basic principle that sub-project permissions and artifact permissions
can *allow* additional access, but can't *restrict* it beyond
what permissions are allowed by a higher level project.

Permission predicates
---------------------

Predicates are simple functions, several of which are defined in Allura
itself, and which can be added by any tool, which return true if
permission is granted, and false if it is not.

An example predicate function `has_project_access` takes two params, an object
and a `permission` string.  It then checks to see if the current user
(picked up from the environment) has permission to perform that action on
that object, following the rules above.
