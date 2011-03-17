from allura.lib.decorators import task, event_handler

@task
def event(event_type, *args, **kwargs):
    event_handler.fire_event(event_type, *args, **kwargs)
