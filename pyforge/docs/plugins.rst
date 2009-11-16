Writing Plugins for PyForge
=====================================================================


Writing applications that run in pyforge
---------------------------------------------------------------------

TODO: Basics of app writing here.   HelloWiki tutorial in the 
tutorials section. 


Writing event listeners
---------------------------------------------------------------------

TODO: write about event listeners in general

Types of event hooks you can use: 

* Immediate, best effort
* Queue based, will be processed (eventually)

Writing your own WebHooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In general it's best to use a BusHook  when writing web hooks 
because you get higher performance and you don't slow down
the queue processing.

Extending the pyforge markup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is a special kind of queue based pluging that allows you to
extend the standard artifact reference system to add new artifact
types (eg: sf:tg:ticket:149) and extend the syntax of our markup
language (based on  Waylan Limberg's excellent markdown implementation
for python). 

http://www.freewisdom.org/projects/python-markdown


