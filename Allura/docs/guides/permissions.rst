Guide to Users, Groups and Permissions in Allura
=====================================================================

User/Group model
---------------------------------------------------------------------

In the allura system `users` can be assigned to various `groups` or
roles on a per-project basis.

Users can be members of many groups, and `groups` can
be assigned a list of `permissions` like `edit`,
`mdoderate` or `read`.   Tools can define their own
set of permissions, for their artifacts.

Individual artifacts and ACL's
---------------------------------------------------------------------

You may want to assign a permission
to particular people or roles for a specific `Artifact` such as
one bug in the ticket tracker.  The Allura platform supports this via
an additive ACL field on every `Artifact` instance.  It is not exposed
via the UI currently.

Permission hierarchy
--------------------------------------------------------------------

Projects and subprojects can define user groups, but for any particular
subproject the set of groups the user belongs to is additive.  This follows
the basic principle that sub-project permissions and artifact permissions
can *allow* additional access, but can't *restrict* it beyond
what permissions are allowed by a higher level project.

Permission predicates
---------------------------------------------------------------------

Predicates are simple functions, several of which are defined in Allura
itself, and which can be added by any tool, which return true if
permission is granted, and false if it is not.

An example predicate function `has_project_access` takes two params, an object
and a `permission` string.  It then checks to see if the current user
(picked up from the environment) has permission to perform that action on
that object, following the rules above.
