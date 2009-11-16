Why not improve existing tools like Trac, Redmine or Bugzilla? 
---------------------------------------------------------------

One word.  Scalability. 

Ok, two words.  Scalability and Performance

Ok, three words:  Scalability, Performance, and Flexibility

Seriously though, we didn't think that any of the existing systems have actually hit the right usibility targets, and we knew that it would be a **lot** of work to get any of them to scale up to the level we needed.

But we knew e-mail integration was going to be a big deal to our forge, so we did take a long look at Roundup, which is a very well designed system build from the ground up around the idea of e-mail integration.

If you were so inspired by Roundup, why not just use it?
---------------------------------------------------------------

We liked the flexible schema system provided by Roundup's HyperTable layer, but thought that native MongoDB bindings were both cleaner, faster, and ultimately more powerful.  Sure we sacrifice the flexibility of Roundup's backend, but our main goal is to make usable, high performance system, not to maximize the number of backend storages systems supported.


---------------------------------------------------------------

---------------------------------------------------------------

---------------------------------------------------------------