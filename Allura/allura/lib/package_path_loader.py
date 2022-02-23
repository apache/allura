#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""
A Jinja template loader which allows for:

- dotted-notation package loading
- search-path-based overriding of same

Dotted notation
---------------

- Allow a Tool implementer to use a dotted-notation module name
  (as occuring in the ``PYTHONPATH``), then the given path within the
  module::

        @expose('jinja:<module.name>:<path/within/module.html>')

  e.g.::

        @expose('jinja:allura:templates/repo/file.html')

Overriding dotted notation
--------------------------

Allow a Tool implementer to override the theme baseline (or any
other Tool's) templates. This can be lighter-weight than subclassing
:class:`allura.plugin.ThemeProvider`, plus will allow for more fine-grained
changes.

This will also override ``extends`` and ``import`` Jinja tags.

This approach uses a:

- ``setup.py`` entry point to a class with...
- *magic* files and...
- (optionally) a class property to specify ordering

File Structure for Overriding dotted notation
=============================================

For the examples, assume the following directory structure::

    NewTool/
    |- setup.py                     <- entry point specified here
    |- newtool/
       |- app.py                    <- entry point target here
       |- templates/
       |  |- index.html             <- Tool's regular templates
       |- override                  <- override_root
          |- allura/                <- magic directory named after module
             |- templates/
                |- repo/
                   |- file.html     <- actual template

To override the above example, a Tool implementer would
add the following line to their Tool's ``setup.py`` (assuming usage in Allura,
with the default ``app_cfg``)::

    [allura.theme.override]
    newtool = newtool.app:NewToolApp

Then, in the neighbor path (see below) for the file containing the
Tool class, add the following path/file::

    override/allura/templates/repo/file.html

The template will be overridden. Note that after changing
``setup.py``, it would be required to re-initialize with setuptools::

    python setup.py develop

Specifying search path order with template_path_rules
=====================================================

If a highly specific ordering is required, such as if multiple Tools
are trying to override the same template, the entry point target
class can also contain a class property template_path_rules::

    class NewToolApp(Application):
        template_path_rules = [
            ['>', 'old-tool'],
        ]

Each rule specifies a postioner and an entry point or "signpost".
If no rule is provided, the default is ``['>', 'allura']``.

The "signposts" are:

- Any other app's override entry point name
- ``site-theme``
- ``allura`` (you probably shouldn't do this)
- ``project-theme`` **NOT IMPLEMENTED**
- ``tool-theme`` **NOT IMPLEMENTED**

The positioners are:

    >
        This overrider will be found BEFORE the specified entry point

    <
        This overrider will be found AFTER the specified entry point

    =
        This will replace one of the "signpost" entry points (if multiple apps
        try to do this for the same signpost, the result is undefined)

**TODO:** Support multiple partial themes

"""
import pkg_resources
import os

import jinja2
from tg import config
from paste.deploy.converters import asbool
from ming.utils import LazyProperty

from allura.lib.helpers import topological_sort, iter_entry_points


class PackagePathLoader(jinja2.BaseLoader):

    def __init__(self, override_entrypoint='allura.theme.override',
                 default_paths=None,
                 override_root='override',
                 ):
        '''
        Set up initial values... defaults are for Allura.
        '''
        # TODO: How does one handle project-theme?
        if default_paths is None:
            default_paths = [
                #['project-theme', None],
                ['site-theme', None],
                ['allura', '/'],
            ]

        self.override_entrypoint = override_entrypoint
        self.default_paths = default_paths
        self.override_root = override_root

    @LazyProperty
    def fs_loader(self):
        return jinja2.FileSystemLoader(self.init_paths())

    def _load_paths(self):
        """
        Load all the paths to be processed, including defaults, in the default order.
        """
        paths = self.default_paths[:]  # copy default_paths
        paths[-1:0] = [  # insert all eps just before last item, by default
            [ep.name, pkg_resources.resource_filename(ep.module_name, "")]
            for ep in iter_entry_points(self.override_entrypoint)
        ]
        return paths

    def _load_rules(self):
        """
        Load and pre-process the rules from the entry points.

        Rules are specified per-tool as a list of the form:

            template_path_rules = [
                    ['>', 'tool1'],  # this tool must be resolved before tool1
                    ['<', 'tool2'],  # this tool must be resolved after tool2
                    ['=', 'tool3'],  # this tool replaces all of tool3's templates
                ]

        Returns two lists of rules, order_rules and replacement_rules.

        order_rules represents all of the '>' and '<' rules and are returned
        as a list of pairs of the form ('a', 'b') indicating that path 'a' must
        come before path 'b'.

        replacement_rules represent all of the '=' rules and are returned as
        a dictionary mapping the paths to replace to the paths to replace with.
        """
        order_rules = []
        replacement_rules = {}
        for ep in iter_entry_points(self.override_entrypoint):
            for rule in getattr(ep.load(), 'template_path_rules', []):
                if rule[0] == '>':
                    order_rules.append((ep.name, rule[1]))
                elif rule[0] == '=':
                    replacement_rules[rule[1]] = ep.name
                elif rule[0] == '<':
                    order_rules.append((rule[1], ep.name))
                else:
                    raise jinja2.TemplateError(
                        'Unknown template path rule in {}: {}'.format(
                            ep.name, ' '.join(rule)))
        return order_rules, replacement_rules

    def _sort_paths(self, paths, rules):
        """
        Process all '>' and '<' rules, providing a partial ordering
        of the paths based on the given rules.

        The rules should already have been pre-processed by _load_rules
        to a list of partial ordering pairs ('a', 'b') indicating that
        path 'a' should come before path 'b'.
        """
        names = [p[0] for p in paths]
        # filter rules that reference non-existent paths to prevent "loops" in
        # the graph
        rules = [r for r in rules if r[0] in names and r[1] in names]
        ordered_paths = topological_sort(names, rules)
        if ordered_paths is None:
            raise jinja2.TemplateError(
                'Loop detected in ordering of overrides')
        return paths.sort(key=lambda p: ordered_paths.index(p[0]))

    def _replace_signposts(self, paths, rules):
        """
        Process all '=' rules, replacing the rule target's path value with
        the rule's entry's path value.

        Multiple entries replacing the same signpost can cause indeterminate
        behavior, as the order of the entries is not entirely defined.
        However, if _sort_by_rules is called first, the partial ordering is
        respected.

        This mutates paths.
        """
        p_idx = lambda n: [e[0] for e in paths].index(n)
        for target, replacement in rules.items():
            try:
                removed = paths.pop(p_idx(replacement))
                paths[p_idx(target)][1] = removed[1]
            except ValueError:
                # target or replacement missing (may not be installed)
                pass

    def init_paths(self):
        '''
        Set up the setuptools entry point-based paths.
        '''
        paths = self._load_paths()
        order_rules, repl_rules = self._load_rules()

        self._sort_paths(paths, order_rules)
        self._replace_signposts(paths, repl_rules)

        return [p[1] for p in paths if p[1] is not None]

    def get_source(self, environment, template):
        '''
        Returns the source for jinja2 rendered templates. Can understand...
        - path/to/template.html
        - module:path/to/template.html
        '''
        # look in all of the customized search locations...
        if not asbool(config.get('disable_template_overrides', False)):
            try:
                parts = [self.override_root] + template.split(':')
                if len(parts) > 2:
                    parts[1:2] = parts[1].split('.')
                return self.fs_loader.get_source(environment,
                                                 os.path.join(*parts))
            except jinja2.TemplateNotFound:
                # fall-back to attempt non-override loading
                pass

        if ':' in template:
            package, path = template.split(':', 2)
            filename = pkg_resources.resource_filename(package, path)
            return self.fs_loader.get_source(environment, filename)
        else:
            return self.fs_loader.get_source(environment, template)
