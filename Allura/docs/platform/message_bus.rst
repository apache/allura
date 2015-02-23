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
Message Bus
***********

Guide to the Allura task and event system
=========================================

Our event system is driven by a MongoDB-based queuing system, most of which you
can ignore, because we've simplified it down to two ideas: *tasks* and *event handlers*.

Glossary
--------

Before we get into the details perhaps a few definitions are in order:

* **app** -- tool for allura such as the tracker, scm, or wiki apps
* **task** -- callable defined in a app that gets invoked by the `taskd` daemon
* **event handler** -- callable defined in an app that gets called on message
  events.  Event handlers are identified by a string name, so a single event can
  fan out to multiple callables.

Tasks
-----

The `MonQTask` class is central to the Allura asynchronous processing system.
Simply put, a `MonQTask` is a document in MongoDB that contains a context
(project/app/user), a function pointer (specified as a dotted string), and
arguments to that function.  Tasks are scheduled by creating `MonQTask`
documents, and the `taskd` daemon executes them as though they were happening in
the web context.

To simplify the use of tasks, Allura provides a decorator `@task` that marks a
function as 'taskable.'  This decorator adds a `.post` method to the function
object that allows the function to be scheduled as a MonQTask.  For instance, the
`commit` task (flushing Solr caches) is defined in as the following::

    @task
    def commit():
        g.solr.commit()

In order to schedule this task for execution by taskd, simply use the `.post`
method::

    commit.post()

If we wanted to call `commit` directly (e.g. in a test), we can still do that as
well::

    commit()

.. _events:

Events
------

Events provide fanout capability for messages, letting several functions get
called in response to the same 'event.'  To note a function as an event handler,
you use the `@event_handler` decorator.  For instance, there is an event handler
on all project updates to subscribe the project's admins to project changes::

    @event_handler('project_updated')
    def subscribe_admins(topic):
        c.app.subscribe_admins()

In order to invoke all the event handlers for a particular topic, we use the
`g.post_event` helper::

    g.post_event('project_updated')

Under the covers, this is scheduling an `event` task that calls all the handlers
for a particular named event.  Note that you can pass arguments (\*args, and
\*\*kwargs) to event handlers just like you do to tasks, with the exception that
the topic name (above, this would be 'project_updated') is always the first
parameter passed to the event handler.

Running the Task Daemon
-----------------------

In order to actually run the asynchronous tasks, we have written a paster command
`taskd`.  This creates a configurable number of worker processes that watch for
changes to the `MonQTask` collection and execute requested tasks.  `taskd` can be
run on any server, but should have similar access to the MongoDB databases and
configuration files used to run the web app server, as it tries to replicate the
request context as closely as possible when running tasks.
