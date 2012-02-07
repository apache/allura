'''
A Jinja template loader which allows for:
 - dotted-notation package loading
 - search-path-based overriding of same

## Dotted notation
- Allow a Tool implementer to use a dotted-notation module name
  (as occuring in the PYTONPATH), then the given path within the
  module:

        @expose('jinja:module.name:path/within/module.html>')

  e.g.

        @expose('jinja:allura:templates/repo/file.html')

## Overriding dotted notation
Allow a Tool implementer to override the theme baseline (or any
other Tool's) templates. This can be lighter-weight than subclassing
allura.plugin.ThemeProvider, plus will allow for more fine-grained
changes.

This will also override `extends` and `import` Jinja tags.

This approach uses a:

- setup.py entry point to a class with...
- _magic_ files and...
- (optionally) a class property to specify ordering

### File Structure for Overriding dotted notation
For the examples, assume the following directory structure:

    NewTool/
    |- setup.py                     <- entry point specified here
    |- newtool/
       |- app.py                    <- entry point target here
       |- templates/
          |- index.html             <- Tool's regular templates
          |- allura/                <- magic directory named after module
             |- templates/
                |- repo/
                   |- file.html     <- actual template

To override the above example, a Tool implementer would
add the following line to their Tool's setup.py:

    [allura.theme.override]
    newtool = newtool.app:NewToolApp

Then, in the neighbor path (see below) for the file containing the
Tool class, add the following path/file:

    templates/allura/templates/repo/file.html

The template will be overridden. Note that after changing
setup.py, it would be required to re-initialize with setuptools:

    python setup.py develop

###  Specifying search path order with template_path_rules
If a highly specific ordering is required, such as if multiple Tools
are trying to override the same template, the entry point target
class can also contain a class property template_path_rules:

    class NewToolApp(Application):
        template_path_rules = [
            ['>', 'old-tool'],
        ]

Each rule specifies a postioner and an entry point or "signpost".
If no rule is provided, the default is ['>', 'allura'].

The "signposts" are:

- site-theme
- allura (you probably shouldn't do this)
- project-theme NOT IMPLEMENTED
- tool-theme NOT IMPLEMENTED

The positioners are:
- >
    - This overrider will be found BEFORE the specified entry point
- <
    - This overrider will be found AFTER the specified entry point... not
      exectly sure why you would use this.
- =
    - This will replace one of the "signpost" entry points... if multiple
      entry points try to do this, the result is undefined.
      TODO: Support multiple partial themes
'''
import pkg_resources
import os

import jinja2


class PackagePathLoader(jinja2.BaseLoader):
    '''
    Implements the following extensions to the BaseLoader for locating
    templates: dotted-notation module-based template loading, and overriding
    the same with other Tools.
    '''
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
                    #['projec-theme', None],
                    ['site-theme', None],
                    ['allura', '/'],
                ]

        self.override_entrypoint = override_entrypoint
        self.default_paths = default_paths
        self.override_root = override_root

        # Finally instantiate the loader
        self.fs_loader = jinja2.FileSystemLoader(self.init_paths())

    def init_paths(self):
        '''
        Set up the setuptools entry point-based paths.
        '''
        paths = self.default_paths[:]

        '''
        Iterate through the overriders.
        TODO: Can this be moved to allura.app_globals.Globals, or is this
              executed before that is available?
        '''
        epoints = pkg_resources.iter_entry_points(self.override_entrypoint)
        for epoint in epoints:
            overrider = epoint.load()
            # Get the path of the module
            tmpl_path = pkg_resources.resource_filename(
                overrider.__module__,
                ""
            )
            # Default insert position is right before allura(/)
            insert_position = len(paths) - 1

            rules = getattr(overrider, 'template_path_rules', [])

            # Check each of the rules for this overrider
            for direction, signpost in rules:
                sp_location = None

                # Find the signpost
                try:
                    sp_location = [path[0] for path in paths].index(signpost)
                except ValueError:
                    # Couldn't find it, hope they specified another one, or
                    # that the default is ok.
                    continue

                if direction == '=':
                    # Set a signpost. Behavior if already set is undetermined,
                    # as entry point ordering is undetermined
                    paths[sp_location][1] = tmpl_path
                    # already inserted! our work is done here
                    insert_position = None
                    break
                elif direction == '>':
                    # going to put it right before the signpost
                    insert_position = min(sp_location, insert_position)
                elif direction == '<':
                    # going to put it right after the signpost
                    insert_position = min(sp_location + 1, insert_position)
                else:
                    # don't know what that is!
                    raise Exception('Unknown template path rule in %s: %s' % (
                        overrider, direction))

            # in the case that we've already replaced a signpost, carry on
            if insert_position is not None:
                # TODO: wouldn't OrderedDict be better? the allura.lib one
                #       doesn't support ordering like the markdown one
                paths.insert(insert_position, (epoint.name, tmpl_path))

        # Get rid of None paths... not useful
        return [path for name, path in paths if path is not None]

    def get_source(self, environment, template):
        '''
        Returns the source for jinja2 rendered templates. Can understand...
        - path/to/template.html
        - module:path/to/template.html
        '''
        package, path = None, None
        src = None
        bits = template.split(':')
        if len(bits) == 2:
            # splitting out the Python module name from the template string...
            # the default allura behavior
            package, path = template.split(':')
            # TODO: is there a better way to do this?
            path_fragment = os.path.join(self.override_root, package, path)
        elif len(bits) == 1:
            # TODO: is this even useful?
            path = bits[0]
            path_fragment = os.path.join(self.override_root, path)
        else:
            raise Exception('malformed template path')

        # look in all of the customized search locations...
        try:
            src = self.fs_loader.get_source(environment, path_fragment)
        except Exception:
            # no Tool implemented an override... not even sure if this will
            # throw an error, but we're ready for it!
            pass

        # ...but if you don't find anything, fall back to the explicit package
        # approach
        if src is None and package is not None:
            # gets the absolute filename of the template
            filename = pkg_resources.resource_filename(package, path)
            # get the filename relative to the fs root (/).. if this fails
            # this error is not caught, so should get propagated normally
            src = self.fs_loader.get_source(environment, filename)
        elif src is None:
            raise Exception(('Template %s not found in search path ' +
                  'and no module specified') % (
                    path,
                  ))
        return src
