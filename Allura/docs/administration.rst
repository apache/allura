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

Administration
=================

Commands, Scripts, and Tasks
----------------------------

Allura has many `paster` commands and `paster` scripts that can be run from the
server commandline to administrate Allura.  There are also tasks that can be
run through the `taskd` system.  New tasks can be submitted via the web at
/nf/admin/task_manager  Some paster commands and scripts have been set up
so that they are runnable as tasks too, giving you the convenience of starting
them through the web and letting `taskd` execute them, rather than from a server
shell.

Commands can be discovered and run via the `paster` command when you are in the
'Allura' directory that has your .ini file.  For example::

    (env-allura) Allura$ paster help
    ... all commands listed here ...

    (env-allura) Allura$ paster create-neighborhood --help
    ... specific command help ...

    (env-allura) Allura$ paster create-neighborhood development.ini myneighborhood myuser ...


Scripts are in the `scripts/` directory and run via `paster script`.  An extra
`--` is required to separate script arguments from paster arguments.  Example::

    (env-allura) Allura$ paster script development.ini ../scripts/create-allura-sitemap.py -- --help
    ... help output ...

    (env-allura) Allura$ paster script development.ini ../scripts/create-allura-sitemap.py -- -u 100


TODO: explain how to run tasks, explain important scripts, commands and tasks here


Client Scripts
--------------

Allura includes some client scripts that use Allura APIs and do not have to be run
from an Allura server.  They do require various python packages to be installed
and possibly a local Allura codebase set up.

One such script is `wiki-copy.py` which reads the wiki pages from one Allura wiki
instance and uploads them to another Allura wiki instance.  It can be run as::

$ python scripts/wiki-copy.py --help
