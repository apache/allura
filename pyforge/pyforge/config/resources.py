import pkg_resources

def register_ew_resources(manager):
    manager.register_directory(
        'js', pkg_resources.resource_filename('pyforge', 'lib/widgets/resources/js'))
    manager.register_directory(
        'css', pkg_resources.resource_filename('pyforge', 'lib/widgets/resources/css'))