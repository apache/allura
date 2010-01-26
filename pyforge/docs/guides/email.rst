Guide to email integration in the PyForge
=====================================================================

Email routing
---------------------------------------------------------------------

routing mechanism will be a dotted path from the project to 
the application/plugin to the specific artifact within that app that is 
used like this::

    subproject.app.artifact@project.example.com

Which would translate into the devtools project which is a subproject of 
turbogears, and it's bug tracer and issue 142 in that tracker:: 

    devtools.bug.142@turbogears.sf.net
    

And it in turn would be published to the message bus, which will assure
that all plugins that are registered to be notified for that e-mail 
addresses are called like that. 

If your app has more than one artifact type, you could nest them inside 
`project.app.something.id.*`

If you were working with the bug tracker directly on the TurboGears project:: 

    bug.142@turbogears.sf.net
    
The PyForge platform allows you to setup other message types, such as commit 
messages, to go into amqp with the same routing information, and turn into 
"messages" just like e-mail. 

Email Content Handling
---------------------------------------------------------------------

On the new forge message bodies should be composed as markdown.  
Multi-part mime encoded messages should be sent include plain text 
(the markdown) and html (rendered from the markdown).

Users are allowed to register that they want plain text only. 

The html2text tool written in python was offered as a way to turn HTML 
formatted e-mails that we recieve into plain text that is formatted in a 
markdown compatible way.  We will have to investigate this a bit more, but it 
looks like a great idea. 

We discussed using a special syntax and set of lines at the top of the 
message to indicate metadata:: 

    Title:   My Document
    Summary: A brief description of my document.
    Authors: Waylan Limberg, John Doe
    Date:    October 2, 2007
    base_url: http://example.com
    
    This is the first paragraph of the document.

The format for this syntax was developed in our original PyForge requirements
doc, and is pretty much exactly the same as what's used by an existing 
markdown extension (markdown-meta), so with two independent implementations, 
we decided that it was the "natural" way to report metadata in e-mail message 
bodies. 

We will also include some text in the footer of the e-mail message with a
link to the message online.   We can use this link to guess where in the
thread the message belongs in the case of a messed up e-mail client that
does not set the the headers for the reply properly. 

The nice thing about this is that it's pretty much already implemented 
for us via the meta plugin. 

This metadata syntax will let you set fields on tickets and otherwise 
interact with the system via e-mail, assuming you have such permissions. 

Spam
---------------------------------------------------------------------

A production deployment of PyForge is likely to have some spam pre-filtering
applied as a first layer of spam defense.   The second layer will be some 
in-app bayesian filtering done inside the Lamson python server that's 
included in PyForge itself. 

We'll build a web UI where user feedback can be turned into data that 
feeds back to the bayesian filter training.   We will also have to build some 
level of user moderation into the system, based on what's done at slashdot 
already.   

Spam prevention technology is a rabbit hole down which the PyForge could go 
forever, without finding a prefect solution.   The goal for launch is not 
perfection, but a solid foundation on which future anti-spam measures 
can be taken. 