Platform Tour
=================

Introduction
---------------

The new Forge is implemented as a collection of plugin applications on top of a
robust and open platform.  Some of the services provided by the platform include:

- Indexing and search
- Authentication and Authorization
- Email integration (every plugin application gets its own email address)
- Asynchronous processing via RabbitMQ
- Simple autolinking between different artifacts in the forge
- Attachment handling
- Plugin administration

Plugins, on the other hand, provide the actual user interface and logic to
manipulate forge artifacts.  Some of the plugins currently impemented include:

admin
  This plugin is installed in all projects, and allows the administration of the
  project's plugins, authentication, and authorization
search
  This plugin is installed in all projects, and provides the ability to search a
  project for various types of artifacts.
home
  This plugin is installed in all projects, and provides the ability to customize
  the project landing page with "widgets" shared by other plugins.
SCM
  This plugin allows you to host a version control system in the
  Forge.  It also provides the ability to "fork" another SCM in order to provide
  your own extensions.
Wiki
  This plugin provides a basic wiki with support for comments, attachments, and
  notifications.
Tracker
  This plugin provides an extensible ticketing system for tracking feature
  requests, defects, or support requests.
Forum
  This plugin provides a forum interface with full email integration as well.
  The forum also handles attachments to posts either via the web interface or via email.

Ming Databases and the Context Object
---------------------------------------------------

There are a few databases you need to be aware of when developing for the new
Forge.  The Forge maintains a 'main' database which contains the project index
and user list as well as a project-local database for each project (sub-projects
share databases with thier parent databases, however).  Most of the time, you
should not need to worry about these databases as they are automatically
managed.  The automatic management is based on various properties of the Pylons
"context" object `c`:

project
  The current project, used to determine which database to use for
  other objects
app
  The current plugin application object.
user
  The current user

The Forge platform provides the following functions to manage the context object:

.. function:: pyforge.lib.helpers.push_config(obj, **kw)
   :noindex:
   
   Context manager (used with the `with` statement) used to temporarily set the
   attributes of a particular object, resetting them to their previous values
   at the end of the `with` block.  Used most frequently with the context object
   `c`::

       c.project = some_project
       with push_config(c, project=other_project):
           ...
           # code in this block will have c.project == other_project
       # code here will have c.project == some_project

.. function:: pyforge.lib.helpers.set_context(project_id, mount_point=None, app_config_id=None)
   :noindex:

   Set the context object `c` according to the given `project_id` and optionally either a
   `mount_point`, an `app_config_id`.  `c.project` is set to the corresponding
   project object.  If the mount_point or app_config_id is
   specified, then `c.app` will be set to the corresponding plugin application
   object.  


Artifacts
-------------

We've mentioned artifacts a couple of times now without definition.  An artifact,
as used in the new Forge, is some object that a plugin needs to store in the
forge.  The platform provides facilities for controlling access to individual
artifacts if that's what the plugin designer favors.  For instance, the Forum
plugin allows a user to edit or delete their own posts, but not to edit or delete
others (unless the user has the 'moderate' permission on the forum itself).
Some examples of artifacts in the current plugins:

- Forum: Forum, Thread, Post, Attachment
- Wiki: Page, Comment, Attachment
- Tracker: Ticket, Comment, Attachment
- SCM: Repository, Commit, Patch

In order to implement your own artifact, you should override at least a few of
the methods of the `pyforge.model.artifact.Artifact` class::

    from ming.orm.property import FieldProperty
    from pyforge.model import Artifact

    class NewArtifact(Artifact):
        class __mongometa__:
            name='my_new_artifact' # collection where this artifact is stored
        type_s = 'My Artifact' # 'type' of the artifact used in search results

        # Add your own properties here (beyond those provided by Artifact)
        shortname = FieldProperty(str)

        def url(self):
            'Each artifact should have its own URL '
            return self.app.url + self.shortname + '/'
    
        def index(self):
            'Return the fields you want indexed on this artifact'
            result = Artifact.index(self)
            result.update(type_s=self.type_s,
                          name_s=self.shortname,
                          text=self.shortname)
            return result

        def shorthand_id(self):
            'Used in the generation of short links like [my_artifact]'
            return self.shortname

Platform services provided for artifacts
---------------------------------------------------

Whenever you create, modify, or delete an artifact, the platform does a couple of
things for you:

- The artifact is added to the index and will appear in searches
- A shortlink is generated for the artifact (e.g. [MyWikiPage]).  This allows you
  to reference the artifact from other artifacts.  For instance, you might want
  to reference `[Ticket#151]` from `[Commit#abac332a]`.  Whenever the commit message
  is displayed in the SCM plugin, any references to `[Ticket#151]` will be
  automatically linked to that Ticket's page.

Shortlinks work only within a project hierarchy (in order to link to some other project's
page, you'll have to use the full URL).  Sometimes, a shortlink may need to be
differentiated based on its location in a subproject or in one of many plugins of
the same type within a project.  In order to do this, shortlinks may be prefixed
by either the plugin mount point or a project ID and plugin mount point.  

For
instance, suppose we have an ticket tracker mounted at `projects/test/tracker`
with Ticket #42 in it.  Further suppose that there is an SCM repository mounted at
`projects/test/subproject/repo`.  A user could push a commit to that repository
with the commit message `[projects/test:tracker:42] - Fix weird issue`.  If you
then examined the commit in the SCM plugin, the shortlink would be clickable and
would take you to the ticket itself.  The Tracker plugin would also list the
commit message as a "related object" in a sidebar to allow for quick cross-referencing.

Asynchronous Processing
-----------------------------------------

Much of the actual functionality of the new Forge comes from code that runs
*outside* the context of a web request, in the `reactor` server (invoked by
running `paster reactor development.ini`.  Asynchronous processing is performed
by two types of functions, *auditors* and *reactors*, differentiated as follows:

Auditor
    Auditors listen to queues on the `audit` exchange.
    Messages sent to an auditor queue are interpreted *imperatively* ("do this").
    Auditor-type messages should specify a project ID `project_id`, an
    application mount point `mount_point`, and a user ID `user_id`, which will be
    used by the platform to set the context before calling the registered
    callback, and all of which reference the *recipient* of the message.  An
    auditor callback function is called *once* for each message received on its queue.
Reactor
    Reactors listen to queues on the `react` exchange.
    Messages sent to a reactor queue are interpreted in an *advisory* manner
    ("this was done").  Reactor-type messages should specify a project ID
    `project_id` and a user ID `user_id`, which will be
    used by the platform to set the context before calling the registered
    callback, and all of which reference the *source* of the message.  If the
    reactor callback is an instance method, it will be called once for each
    instance of the plugin that exists for the given project for each message
    received on its queue.  If it is a class method, it will be called once for
    each message received on its queue.  For instance, the Tracker plugin may be
    configured to react to SCM commit messages in order to generate links between
    SCM commits and Tracker tickets.  *All tracker instances* in a project will
    be notified of SCM commits in such a case.

In order to create a callback function for an auditor or a reactor, simply add a
method to the plugin application class that is decorated either with the `@audit`
or the `@react` decorator.  For instance, the forum plugin defines a reactor on
the `Forum.new_post` message::

    @react('Forum.new_post')
    def notify_subscribers(self, routing_key, data):
        ....

If there are a large number of reactors, you can define them in a separate module
and use the `mixin_reactors()` method as in the SCM plugin::

    from .reactors import common_react, hg_react, git_react, svn_react
    ...
    class ForgeSCMApp(Application):
        ...
    mixin_reactors(ForgeSCMApp, common_react)
    mixin_reactors(ForgeSCMApp, hg_react)
    mixin_reactors(ForgeSCMApp, git_react)
    mixin_reactors(ForgeSCMApp, svn_react)

.. sidebar:: Updating auditors and reactors

   If you add, remove, or change the routing key of any auditor or reactor,
   chances are that you'll need to re-configure the rabbitmq server to handle the
   queue changes.  To do this, you need simply to run the following command::

       $ paster reactor_setup development.ini

   This will tear down all the queues and recreate them based on the code that
   currently exists.

In order to actually *send* a message to either the `audit` or `react` exchange,
a helper method is provided in the pylons global object `g`:

.. method:: pyforge.lib.app_globals.AppGlobals.publish(xn, key, message=None, **kw)
   :noindex:
   
   Used to send messages to the named exchange.  This method will automatically
   set the message attributes `project_id`, `mount_point`, and `user_id` based on
   the current context.

   :param xn: exchange name (either "audit" or "react")
   :param key: routing key (e.g. "Forum.new_post")
   :param message: optional dictionary with message content
   :param kw: optional keyword arguments which are passed through to the `carrot.Publisher`

Email Integration
-----------------------------------------

The Forge platform provides easy-to-use email integration.  Forge email addresses
are of the form
<topic>@<mount_point>[.<subproject>]*.<subproject>.projects.sourceforge.net.
When a message is received on such an email address, the address is parsed and
the sending user is identified (if possible).  Based on the parsed address, the
pylons context attributes `c.project` and `c.app` are set, and the application is
queried to determine whether the identified user has authority to send an email
to the given app/topic combination by calling `c.app.has_access(user, topic)`.
If the user has access, the message is decomposed into its component parts (if a
multipart MIME-encoded message) and one `audit` message is generated for each
part with the following fields:

headers
  The actual headers parsed from the body of the message
message_id
  The `Message-ID` header (which should be universally
  unique and is 
  generated by the email client), used for determining which messages are replies
  to which other messages
in_reply_to
  The `In-Reply-To` header, used for determining which messages are replies to
  which other messages
references
  The `References` header, used for determining which messages refer to
  which other messages
filename
  Optional, if the part is an attachment with a filename, this will be populated
content_type
  The MIME content_type of the message part
payload
  The actual content of the message part
user_id
  The ID of the user who sent the message

Once the message is generated, it is sent to the `audit` exchange with the
routing key <Plugin Type>.<topic>.  For instance, a message to comment on a Wiki
page might have the routing key `Wiki.MainPage`.

The Forge platform also provides full support for *sending* email without
worrying about the specifics of SMTP or sendmail handling.  In order to send an
email, a plugin needs simply to send an `audit` message with the routing key
`forgemail.send_email` and the following fields:

from
  Return address on the message (usually the topic@plugin_name that generated
  it)
subject
  Subject of the message
message_id
  Value to put in the `Message-ID` header (the `_id` field of a
  :class:`pyforge.model.artifact.Message` is suitable for this)
in_reply_to (optional)
  Value to put in the `In-Reply-To` header (the `parent_id` field of a
  :class:`pyforge.model.artifact.Message` is suitable for this)
destinations
  List of email addresses and/or :class:`pymongo.bson.ObjectId` s for
  :class:`pyforge.model.auth.User` objects
text
  Markdown-formatted body of the message (If the user has requested html or
  combined text+html messages in their preferences, the Markdown will be so
  rendered.  Otherwise a plain text message will be sent.)

Migrations
------------------

Although Ming provides the Forge platform with some lazy migration facilities,
there are some cases (adding an index, dropping an index, etc.) where this is
insufficient.  In these cases, the Forge platform uses the Flyway migration
system.  Migrations are organized into 'modules' which are specified by named
entry points under the 'flyway.migrations' section.  For instance, to specify a
migrations module for the ForgeForum, you might have the following entry point::

    [flyway.migrations]
    forum = forgeforum.migrations

Inside the :mod:`forgeforum.migrations` module, you would specify the various
migration scripts to be run::

    from flyway import Migration

    class V0(Migration):
        version=0
        def up(self):
            # Do some stuff with self.session to upgrade
        def down(self):
            # Do some stuff with self.session to undo the 'up'

    class V1(Migration):
        version=1
        def up(self):
            # Do some stuff with self.session to upgrade
        def down(self):
            # Do some stuff with self.session to undo the 'up'

You can optionally supply a `requires()` method for your migration if it requires
something more complex than the previous migration in the same module::

    class V3(Migration):
        version=3
        def requires(self):
            yield ('pyforge', 3)
            for r in super(V3, self).requires():
                yield r

To actually run the migration, you must call the paster command `flyway`::

    # migrate all databases on localhost to latest versions of all modules
    $ paster flyway

    # migrate the 'pyforge' database on 'myserver' to the latest version
    $ paster flyway -u mongo://myserver:27017/pyforge

    # migrate all the databases on 'myserver' to the latest version
    $ paster flyway -u mongo://myserver:27017/

    # migrate the forgeforum module to the latest version on localhost
    $ paster flyway forgeforum

    # migrate the forgeforum module to the version 5 (up or down) on localhost
    $ paster flyway forgeforum=5

It's often helpful to see exactly what migrations flyway is planning on running;
to get this behavior, pass the option `-d` or `--dry-run` to the flyway command.
