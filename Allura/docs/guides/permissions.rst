Guide to Users, Groups and Permissions in PyForge
=====================================================================

User/Group model
---------------------------------------------------------------------

In the allura system `users` can be assigned to various `groups` or 
roles on a per-project basis.

Users can be members of many groups, and both `users` and `groups` can 
be assigned a list of `permissions` like `add_subproject`, 
`commit_to_master` or `admin_users`.   Tools can define their own
set of permissions, for their artifacts.   Tools are encouraged to
prefix their permissions with the tool name, so for a tool called
"tracker" a good permission name would be `tracker_edit_ticket`.

Individual artifacts and ACL's 
---------------------------------------------------------------------

There are also likely to be some permissions that you want to assign
to particular people or roles for a particular `Artifact` such as 
a particular bug in the ticket tracker.   PyForge supports this via
an ACL field on every `Artifact` instance. 

Permission hierarchy
--------------------------------------------------------------------

Projects and subprojects can define user groups, but for any particular
subproject the set of groups the user belongs to is additive.  This follows
the basic principle that sub-project permissions and artifact permissions
can *allow* additional access, but can't *restrict* it beyond 
what permissions are allowed by a higher level project. 

Permission predicates
---------------------------------------------------------------------

Predicates are simple functions, several of which are defined in PyForge 
itself, and which can be added by any tool, which return true if
permission is granted, and false if it is not. 

An example predicate function `has_project_access` takes two params, an object
and a `permission` string.  It then checks to see if the current user 
(picked up from the environment) has permission to perform that action on 
that object, following the rules above. 



