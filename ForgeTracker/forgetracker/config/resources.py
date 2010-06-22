import pkg_resources

def register_ew_resources(manager):
    manager.register_directory(
        'tracker_js', pkg_resources.resource_filename('forgetracker', 'widgets/resources/js'))
    manager.register_directory(
        'tracker_css', pkg_resources.resource_filename('forgetracker', 'widgets/resources/css'))