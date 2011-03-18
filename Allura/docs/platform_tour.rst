Platform Tour
=================

Introduction
---------------

Allura is implemented as a collection of tool applications on top of a
robust and open platform.  Some of the services provided by the platform include:

- Indexing and search
- Authentication and Authorization
- Email integration (every tool application gets its own email address)
- Asynchronous processing via RabbitMQ
- `Markdown <http://daringfireball.net/projects/markdown/>`_ markup formatting
- Simple autolinking between different artifacts in the forge
- Attachment handling
- Tool administration

Tools, on the other hand, provide the actual user interface and logic to
manipulate forge artifacts.  Some of the tools currently impemented include:

admin
  This tool is installed in all projects, and allows the administration of the
  project's tools, authentication, and authorization
Git, Hg, SVN
  These tools allow you to host a version control system in Allura.
  They also provides the ability to "fork" Git and Hg repos in order to
  provide your own extensions.
Wiki
  This tool provides a basic wiki with support for comments, attachments, and
  notifications.
Tracker
  This tool provides an extensible ticketing system for tracking feature
  requests, defects, or support requests.
Discussion
  This tool provides a forum interface with full email integration as well.
  The forum also handles attachments to posts either via the web interface or via email.

The Context Object
---------------------------------------------------

The Pylons "context" object `c` has several properties which are automatically
set for each request:

project
  The current project
app
  The current tool application object.
user
  The current user

Allura platform provides the following functions to manage the context object,
if you need to change the context for some situation:

.. function:: allura.lib.helpers.push_config(obj, **kw)
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

.. function:: allura.lib.helpers.set_context(project_id, mount_point=None, app_config_id=None)
   :noindex:

   Set the context object `c` according to the given `project_id` and optionally either a
   `mount_point`, an `app_config_id`.  `c.project` is set to the corresponding
   project object.  If the mount_point or app_config_id is
   specified, then `c.app` will be set to the corresponding tool application
   object.


Artifacts
-------------

We've mentioned artifacts a couple of times now without definition.  An artifact,
as used in Allura, is some object that a tool needs to store in the
forge.  The platform provides facilities for controlling access to individual
artifacts if that's what the tool designer favors.  For instance, the Discussion
tool allows a user to edit or delete their own posts, but not to edit or delete
others (unless the user has the 'moderate' permission on the forum itself).
Some examples of artifacts in the current tools:

- Discussion: Forum, Thread, Post, Attachment
- Wiki: Page, Comment, Attachment
- Tracker: Ticket, Comment, Attachment
- SCM: Repository, Commit, Patch

In order to implement your own artifact, you should override at least a few of
the methods of the `allura.model.artifact.Artifact` class::

    from ming.orm.property import FieldProperty
    from allura.model import Artifact

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
- A shortlink is generated for the artifact (e.g. [MyWikiPage] or [#151]).  This allows you
  to reference the artifact from other artifacts.  Whenever the commit message
  is displayed in the SCM tool, any references to `[#151]` will be
  automatically linked to that Ticket's page.

Shortlinks work only within a project hierarchy (in order to link to some other project's
page, you'll have to use the full URL).  Sometimes, a shortlink may need to be
differentiated based on its location in a subproject or in one of many tools of
the same type within a project.  In order to do this, shortlinks may be prefixed
by either the tool mount point or a project ID and tool mount point.

For instance, suppose we have an ticket tracker called 'features' and one called 'bugs'.
They both have many tickets in them.  To distinguish, use the tracker mount point
within the reference.  For example [features:#3] or [bugs:#3]

Asynchronous Processing
-----------------------------------------

Much of the actual functionality of Allura comes from code that runs
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
    instance of the tool that exists for the given project for each message
    received on its queue.  If it is a class method, it will be called once for
    each message received on its queue.  For instance, the Tracker tool may be
    configured to react to SCM commit messages in order to generate links between
    SCM commits and Tracker tickets.  *All tracker instances* in a project will
    be notified of SCM commits in such a case.

In order to create a callback function for an auditor or a reactor, simply add a
method to the tool application class that is decorated either with the `@audit`
or the `@react` decorator.  For instance, the discussion tool defines a reactor on
the `Forum.new_post` message::

    @react('Forum.new_post')
    def notify_subscribers(self, routing_key, data):
        ....

If there are a large number of reactors, you can define them in a separate module
and use the `mixin_reactors()` method as in the SCM tool::

    from .reactors import reactors
    ...
    class ForgeGitApp(Application):
        ...
    mixin_reactors(ForgeGitApp, reactors)

.. sidebar:: Updating auditors and reactors

   If you add, remove, or change the routing key of any auditor or reactor,
   chances are that you'll need to re-configure the rabbitmq server to handle the
   queue changes.  To do this, you need simply to run the following command::

       $ paster reactor_setup development.ini

   This will tear down all the queues and recreate them based on the code that
   currently exists.

In order to actually *send* a message to either the `audit` or `react` exchange,
a helper method is provided in the pylons global object `g`:

.. method:: allura.lib.app_globals.AppGlobals.publish(xn, key, message=None, **kw)
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

The Allura platform provides easy-to-use email integration.  Forge email addresses
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
routing key <Tool Type>.<topic>.  For instance, a message to comment on a Wiki
page might have the routing key `Wiki.MainPage`.

The Allura platform also provides full support for *sending* email without
worrying about the specifics of SMTP or sendmail handling.  In order to send an
email, a tool needs simply to send an `audit` message with the routing key
`forgemail.send_email` and the following fields:

from
  Return address on the message (usually the topic@tool_name that generated
  it)
subject
  Subject of the message
message_id
  Value to put in the `Message-ID` header (the `_id` field of a
  :class:`allura.model.artifact.Message` is suitable for this)
in_reply_to (optional)
  Value to put in the `In-Reply-To` header (the `parent_id` field of a
  :class:`allura.model.artifact.Message` is suitable for this)
destinations
  List of email addresses and/or :class:`bson.ObjectId` s for
  :class:`allura.model.auth.User` objects
text
  Markdown-formatted body of the message (If the user has requested html or
  combined text+html messages in their preferences, the Markdown will be so
  rendered.  Otherwise a plain text message will be sent.)
