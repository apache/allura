Platform Architecture overview
===================================

I'm told that the reason you build a platform is to "reduce the marginal cost of developing applications."  Sounds good.   Well, actually it sounds a bit dry.  But it's about right, we want to make creating new online development tools faster, easier, and more fun, which i guess is the "reduce the marginal cost" thing.

Application Plugins
---------------------------------------------------------------------

Writing a plugin for the new forge is as simple as defining a few controllers to handle particular URL's, templates to render pages, and defining the schemas of any new forge document types that your plugin requires.  

.. image:: _static/images/plugins.png
   :alt: App Plugins
   :align: right

You'll get lots of stuff for free: 

* Search-ability of your Artifacts
* Artifact versioning for accountability and transparency
* Ability to extend existing Artifacts
* Reuse central User/group/permission management
* A robust and flexible permissions system
* Access to a real-time event publishing system

How it works
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We needed a **fast,** flexible, and easy to use data persistence system.  

We wanted app plugins to be able to create and version their own document types, extend existing document structures, and to mange document revisions, access control lists, and other platform level data.  Several of the PyForge authors (including me) used MongoDB in rewriting the download flow of SourceForge.net, and new that it could handle huge loads (we saturated a 2gb network connection on the server with 6% cpu utilization).   Rick Copeland had built a couple of custom Object Non-Relational Mappers (ONRM) before, including one for MongoDB, and he whipped up Ming, which backed on MongoDB and gave us exactly what we needed. 

We also needed a **fast,** flexible event message bus, and queuing system. RabbitMQ was  (lightning) fast, (shockingly) flexible, but not supper easy to use.   Fortunately we didn't have to roll our own wrapper here, as the python community already whipped up Carrot, and Celery, which made working with the RabbitMQ based AMQP bus a LOT easer. 

In order to facilitate more open processes, where more users can contribute -- while still protecting data -- documents can easily be "versioned", and the platform provides tools to manage versioned documents for you.

The most basic app plugin consists of a few things: 

* A controller object (instantiated per request)
* Template files (optional)
* UI Widgets (optional)
* Extensions to existing Artifiacts (optional)
* New Artifact types (optional)
* Event listener plugins (optional)
* Event publisher (optional)



Pluggable Event Listeners
---------------------------------------------------------------------


Web Hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
