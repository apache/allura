Writing event listeners
---------------------------------------------------------------------

Our event system is driven by RabbitMQ, most of which you can ignore,
because we've simplified it down to two kinds of event listeners:

.. image:: _static/images/amqp.png
   :alt: App Tools

Basically you either get:
* Immediate, best effort messages
* Queue based messages will be processed (eventually)

The pyforge platform creates a pool of queue consumers that handle messages,
and it calls all the Reactors that are registered for that event.

Or, you can ask for immediate message receipt, with now guarantee of delivery.

Writing your own WebHooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There's no reason a event listener can't call out over HTTP to some web
service...

TODO: Document reactors that implement web-hooks after we write some ;)


Extending the pyforge markup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is a special kind of queue based tool that allows you to
extend the standard artifact reference system to add new artifact
types (eg: sf:tg:ticket:149) and extend the syntax of our markup
language (based on  Waylan Limberg's excellent markdown implementation
for python).

http://www.freewisdom.org/projects/python-markdown
