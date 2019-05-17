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

*************
Platform Tour
*************

Introduction
^^^^^^^^^^^^

Allura is implemented as a collection of tool applications on top of a
robust and open platform.  Some of the services provided by the platform include:

- Indexing and search
- Authentication and Authorization
- Email integration (every tool application gets its own email address)
- Asynchronous processing with background tasks and events
- `Markdown <http://daringfireball.net/projects/markdown/>`_ markup formatting
- Simple autolinking between different artifacts in the forge
- Attachment handling
- Tool administration

Tools, on the other hand, provide the actual user interface and logic to
manipulate forge artifacts.  Some of the tools currently implemented include:

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
------------------

The TurboGears "context" object `c` has several properties which are automatically
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
---------

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
----------------------------------------

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
-----------------------

Much of the actual functionality of Allura comes from code that runs
*outside* the context of a web request, in the `taskd` server (invoked by
running :command:`paster taskd development.ini`).  Asynchronous processing is performed
by two types of functions, *tasks* and *events*, differentiated as follows:

Task
    Tasks are module-level global functions.  They are annotated with the `@task`
    decorator and are invoked with the `.post` method.  For instance, to schedule
    a task  `foobar` to execute in the `taskd` context, you would write::

       @task
       def foobar(a,b,c=5): ...
       
       foobar.post(9,1,c=15)

Event
    Events are intended for "fan-out" types of events.  Events have a string
    name, and are  "listened" for by using the `@event_handler` decorator.  The
    `g.post_event()` helper is provided to run the event handlers for a
    particular event in the `taskd` context.  Multiple event handlers can be
    registered for each event::

        @event_handler('event_name')
        def handler1(topic, *args, **kwargs): ...

        @event_handler('event_name')
        def handler2(topic, *args, **kwargs): ...

        g.post_event('event_name', 1,2,3, a=5)


Email Integration
-----------------

The Allura platform provides easy-to-use email integration.  Forge email addresses
are of the form
:samp:`<topic>@<mount_point>[.<subproject>].<project>.mysite.com`.
When a message is received on such an email address, the address is parsed and
the sending user is identified (if possible).  Based on the parsed address, the
TurboGears context attributes `c.project` and `c.app` are set, and the application is
queried to determine whether the identified user has authority to send an email
to the given app/topic combination by calling `c.app.has_access(user, topic)`.
If the user has access, the message is decomposed into its component parts (if a
multipart MIME-encoded message) and `c.app.handle_message(topic, message)` is
called for each part with the following components to the `msg` dict:

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

The Allura platform also provides full support for *sending* email without
worrying about the specifics of SMTP or sendmail handling.  In order to send an
email, simply post a task for `allura.tasks.mail_tasks.sendmail` with the
following arguments:

fromaddr
  Return address on the message (usually the topic@tool_name that generated
  it)
destinations
  List of email addresses and/or :class:`bson.ObjectId` s for
  :class:`allura.model.auth.User` objects
text
  Markdown-formatted body of the message (If the user has requested html or
  combined text+html messages in their preferences, the Markdown will be so
  rendered.  Otherwise a plain text message will be sent.)
reply_to
  Address to which replies should be sent
subject
  Subject of the message
message_id
  Value to put in the `Message-ID` header (the `_id` field of a
  :class:`allura.model.artifact.Message` is suitable for this)
in_reply_to (optional)
  Value to put in the `In-Reply-To` header (the `parent_id` field of a
  :class:`allura.model.artifact.Message` is suitable for this)
