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

*****
Email
*****


Email routing
-------------

routing mechanism will be a dotted path from the project to
the application/tool to the specific artifact within that app that is
used like this::

    subproject.app.artifact@project.example.com

Which would translate into the devtools project which is a subproject of
turbogears, and it's bug tracker and ticket 142 in that tracker::

    devtools.bug.142@turbogears.sf.net


And it in turn would be published to the message bus, which will assure
that all tools that are registered to be notified for that e-mail
addresses are called like that.

If your app has more than one artifact type, you could nest them inside
`project.app.something.id.*`

If you were working with the bug tracker directly on the TurboGears project::

    bug.142@turbogears.sf.net


Email Content Handling
----------------------

On Allura message bodies should be composed as markdown.
Multi-part mime encoded messages should be sent include plain text
(the markdown) and html (rendered from the markdown).

Users are allowed to register that they want plain text only.

We will also include some text in the footer of the e-mail message with a
link to the message online.   We can use this link to guess where in the
thread the message belongs in the case of a messed up e-mail client that
does not set the headers for the reply properly.

The nice thing about this is that it's pretty much already implemented
for us via the meta tool.

This metadata syntax will let you set fields on tickets and otherwise
interact with the system via e-mail, assuming you have such permissions.
