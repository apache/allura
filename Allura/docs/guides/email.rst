Guide to email integration in the Allura
=====================================================================

Email routing
---------------------------------------------------------------------

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

The Allura platform allows you to setup other message types, such as commit
messages, to go into amqp with the same routing information, and turn into
"messages" just like e-mail.

Email Content Handling
---------------------------------------------------------------------

On Allura message bodies should be composed as markdown.
Multi-part mime encoded messages should be sent include plain text
(the markdown) and html (rendered from the markdown).

Users are allowed to register that they want plain text only.

We will also include some text in the footer of the e-mail message with a
link to the message online.   We can use this link to guess where in the
thread the message belongs in the case of a messed up e-mail client that
does not set the the headers for the reply properly.

The nice thing about this is that it's pretty much already implemented
for us via the meta tool.

This metadata syntax will let you set fields on tickets and otherwise
interact with the system via e-mail, assuming you have such permissions.
