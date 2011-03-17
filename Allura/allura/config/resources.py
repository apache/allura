import os
import logging

import pkg_resources

log = logging.getLogger(__name__)

def register_ew_resources(manager):
    manager.register_directory(
        'js', pkg_resources.resource_filename('allura', 'lib/widgets/resources/js'))
    manager.register_directory(
        'css', pkg_resources.resource_filename('allura', 'lib/widgets/resources/css'))
    manager.register_directory(
        'allura', pkg_resources.resource_filename('allura', 'public/nf'))
    for ep in pkg_resources.iter_entry_points('allura'):
        try:
            manager.register_directory(
                'tool/%s' % ep.name,
                pkg_resources.resource_filename(
                    ep.module_name,
                    os.path.join('nf', ep.name)))
        except ImportError:
            log.warning('Cannot import entry point %s', ep)
            raise
