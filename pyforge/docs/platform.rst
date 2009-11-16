Platform Architecture overview
===================================

I'm told that the reason you build a platform is to "reduce the marginal cost of developing applications."  Sounds good.   Well, actually it sounds a bit dry.  But it's about right, we want to make creating new online development tools faster, easier, and more fun, which i guess is the "reduce the marginal cost" thing.

But why not just **use** a platform like **TurboGears**, **Django** or **Rails**? Why write our own?   I mean lots of folks have written great web frameworks that reduce the marginal cost of creating web apps like ticket trackers, code review tools, etc.  The simple answer is that we **did** use TurboGears, we can make things easier because we get to **focus** our platform quite a bit, we're not building a generic web framework, we're building the set of development tools that we need to create great online project community experiences.   Add to that the desire to host these tools at SourceForge.net, and scale them up to handle all of our traffic, and we've got something significantly different from a generic web framework. 

One thing we knew is that our underlying infrastructure had to scale well. 

We needed a **fast,** flexible, and easy to use data persistence system.  We wanted app plugins to be able to create and version their own document types, extend existing document structures, and to mange document revisions, access control lists, and other platform level data.  I (Mark) used MongoDB in rewriting the download flow of SourceForge.net, and new that it could handle huge loads (we saturated a 2gb network connection on the server with 6% cpu utilization).   Rick Copeland had built a custom Object (Non-Relational) mapper before, and he whipped up Ming, which backed on MongoDB and gave us exactly what we needed. 

We also needed a **fast,** flexible event message bus, and queuing system.   RabbitMQ was  (lightning) fast, (shockingly) flexible, but not supper easy to use.   Fortunately we didn't have to roll our own wrapper here, as the python community already whipped up Carrot, and Celery, which made working with the RabbitMQ based AMQP bus a LOT easer. 

In order to facilitate more open processes, where more users can contribute -- while still protecting data -- documents can easily be "versioned", and the platform provides tools to manage versioned documents for you.


Application Plugins
-----------------------------------



Pluggable Event Listeners
-----------------------------------

Web Hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


