import pkg_resources

def register_ew_resources(manager):
    manager.register_directory(
        'activity_js', pkg_resources.resource_filename('forgeactivity', 'widgets/resources/js'))
