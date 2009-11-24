Guide to Users, Groups and Permissions in PyForge
=====================================================================

User/Group model
---------------------------------------------------------------------

In the pyforge system `users` can be assigned to various `groups` or 
roles on a per-project basis.

Users can be members of many groups, and both `users` and `groups` can 
be assigned a list of `permissions` like `"add_subproject"`, 
`"commit_to_master"`or "admin_users".   Plugins can define their own 
set of permissions, for their artifacts.   Plugins are encouraged to 
prefix their permissionswith the plugin name so for a pluging called 
"tracker" a good permissin name would be `"tracker_edit_ticket"`

Artifacts and ACL's 
---------------------------------------------------------------------

There are also likely to be some permissions that you want to assign
to particular people or roles for a particular `Artifiact` such as 
a particular bug in the ticket tracker.   PyForge supports this via
an acl field on every `Artifact` instance. 

Permission calculation
--------------------------------------------------------------------

Projects and subprojects can define user `groups`, but for any particular
subproject the groups the user belongs too is additive.  This follows
the basic principle that sub-project permissions and artifiact permissions
can *allow* additional access, but can't *restrict* it beyond 
what permissions are allowed by a higher level project. 

The magic of **predicates**
---------------------------------------------------------------------



