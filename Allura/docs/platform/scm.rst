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

*******************
SCM tools in Allura
*******************


The interface API and most of the controller and view structure of
code repository type apps is defined in the base classes in the
Allura package, which consists of the classes in the following
packages:

* `allura.lib.repository` for the base application and implementation classes
* `allura.controllers.repository` for the base controllers
* `allura.model.repository` for the repo metadata models
* `allura.model.repo_refresh` for the repo metadata refresh logic


Application and Implementation
------------------------------

The `Application` structure for SCM apps follows the normal pattern for
Allura applications, though they should inherit from
`allura.lib.repository.RepositoryApp` instead of `allura.app.Application`.
The apps are then responsible for implementing subclasses of
`allura.lib.repository.Repository` and `allura.lib.repository.RepositoryImplementation`.

The `Repository` subclass is responsible for implementing tool-specific
logic using the metadata models and proxying the rest of its logic to the
`RepositoryImplementation` subclass, which talks directly to the underlying
SCM tool, such as `GitPython`, `Mercurial`, or `pysvn`.

Historically, more was done in the `Repository` subclass using the metadata
models, but we are trying to move away from those toward making the SCM apps
thin wrappers around the underlying SCM tool (see `Indexless`_, below).


Controller / View Dispatch
--------------------------

All of the SCM apps use the base controllers in `allura.controllers.repository`
with only minimal customization through subclassing (primarily to
override the template for displaying instructions for setting up a newly
created repository), so the dispatch for all SCM apps follows the same
pattern.

The root controller for SCM apps is `allura.controllers.repository.RepoRootController`.
This controller has views for repo-level actions, such as forking and merging,
and the SCM app attaches a refs and a commits (ci) controller to dispatch symbolic
references and explicit commit IDs, respectively.  (This should be refactored to be
done in the `RepoRootController` so that the dispatch can be followed more easily.)
(Also, `ForgeSVN` actually eschews this class and uses `BranchBrowser` directly as
its root, in order to tweak the URL slightly, but it monkeypatches the relevant
views over, so the dispatch ends up working more or less the same.)

The refs controller, `allura.controllers.repository.RefsController`, handles
symbolic references, and in particular handles custom escape handling to detect
what is part of the ref name vs part of the remainder of the URL to dispatch.
This is then handed off to the `BranchBrowserClass` which is a pointer to
the implementation within the specific SCM app which handles the empty
repo instructions or hands it back to the generic commits controller.

The commits controller, `allura.controllers.repository.CommitsController`,
originally only handled explicit commit IDs, but was modified to allow for
persistent symbolic refs in the URL ("/p/allura/git/ci/master/", e.g.),
it was changed to have the same escape parsing logic as the refs controller.
Regardless, it just parses out the reference / ID from the URL and hands
off to the commit browser.

The commit browser, `allura.controllers.repository.CommitBrowser`, holds
the views related to a specific commit, such as viewing the commit details
(message and changes), a log of the commit history starting with the commit,
or creating a snapshot of the code as of the commit.  It also has a "tree"
endpoint for browsing the file system tree as of the commit.

The tree browser, `allura.controllers.repository.TreeBrowser`, holds the
view for viewing the file system contents at a specific path for a given
commit.  The only complication here is that, instead of parsing out the
entire tree path at once, it recursively dispatches to itself to build
up the path a piece at a time.  Tree browsing also depends on the
`Last Commit Logic`_ to create the data needed to display the last
commit that touched each file or directory within the given directory.


Last Commit Logic
-----------------

Determining which commit was the last to touch a given set of files or
directories can be complicated, depending on the specific SCM tool.
Git and Mercurial require manually walking up the commit history to
discover this information, while SVN can return it all from a single
`info2` command (though the SVN call will be significantly slower than
any individual call to Git or Mercurial).  Because this can sometimes
be costly to generate, it is cached via the `allura.model.repository.LastCommit`
model.  This will generate the data on demand by calling the underlying
SCM tool, if necessary, but the data is currently pre-generated during
the post-push refresh logic for Git and Mercurial.

The overall logic for generating this data for Git and Mercurial is as follows:

1. All items modified in the current commit get their info from the
   current commit

2. The info for the remaining items is found:

 * If there is a `LastCommit` record for the parent directory, all of
   the remaining items get their info from the previous `LastCommit`

 * Otherwise, the list of remaining items is sent to the SCM implementation,
   which repeatedly asks the SCM for the last commit to touch any of the
   items for which we are missing information, removing items from the list
   as commits are reported as having modified them

3. Once all of the items have information, or if a processing timeout is reached,
   the gathered information is saved in the `LastCommit` model and returned



Indexless
---------

Currently, there are model classes which encapsulate SCM metadata
(such as commits, file system structure, etc) in a generic (agnostic to
the underlying tool implementation) way.  However, this means that we're
duplicating in mongo a lot of data that is already tracked by the
underlying SCM tool, and this data must also be indexed for new repos
and after every subsequent push before the commits or files are browsable
via the web interface.

To minimize this duplication of data and reduce or eliminate the delay
between commits being pushed and them being visible, we are trying to
move toward a lightweight API layer that requests the data from the
underlying SCM tool directly, with intelligent caching at the points
and in the format that makes the most sense to make rendering the SCM
pages as fast as possible.
