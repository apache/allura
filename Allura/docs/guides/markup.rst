Guide to the Allura markup system
=====================================================================

Markup transformations in Allura are implemented as a, surprise surprise, reactor tool.

The markup language in Allura is based on MarkDown (http://daringfireball.net/projects/markdown/)

Other markup languages could be implemented with a new markup reactor tool...

TODO: Is this true, or did we decide to just go with markdown? 

Extending the artifact/link system
---------------------------------------------------------------------

There is a special kind of queue based tool that allows you to
extend the standard artifact reference system to add new artifact
types (eg: sf:tg:ticket:149) and extend the syntax of our markup
language (based on  Waylan Limberg's excellent markdown implementation
for python). 

http://www.freewisdom.org/projects/python-markdown



Extending Markdown itself
---------------------------------------------------------------------


Generic Markup extensions (regular expressions, oh my!)
---------------------------------------------------------------------



