Why not improve existing tools like Trac, Redmine or Bugzilla? 
---------------------------------------------------------------------

One word.  Scalability. 

Ok, two words.  Scalability and Performance

Ok, three words:  Scalability, Performance, and Flexibility

Seriously though, we didn't think that any of the existing systems have 
actually hit the right usability, scalability, or flexibility targets that 
we needed to hit, and we knew that it would be a **lot** of work to get 
any of them to do what we needed.

But we knew e-mail integration was going to be a big deal to our forge, 
so we did take a long look at Roundup, which is a very well designed 
system build from the ground up around the idea of e-mail integration.

If you were so inspired by Roundup, why not just use it?
---------------------------------------------------------------------

We liked the flexible schema system provided by Roundup's HyperTable layer, 
but thought that native MongoDB bindings were both cleaner, faster, and 
ultimately more powerful.  

Sure we sacrifice the flexibility of Roundup's 
backend, but our main goal is to make usable, high performance system, 
not to maximize the number of backend storages systems supported.

Why create all the apps as plugins? 
---------------------------------------------------------------------

We know that some projects are going to want more locked down
access controls in their bug trackers, or more workflow based 
processes.  These things are inevitable, and we really do want
to support them, but at the same time they are going to conflict
with the way many other projects want to work.   

Building a plugin system, and standard integration points
makes it possible to serve everybody in one way or another. 

Why not just allow web-based extensions? 
---------------------------------------------------------------------

We talked about this quite a bit, and decided that we could write local
native plugins more quickly and easily, and that we could build a 
local app plugin that proxied out to an external webapp, and that
we could provide a lot more flexibility by allowing custom
external webapp proxies -- which brought us right back to local 
plugins. 


---------------------------------------------------------------------