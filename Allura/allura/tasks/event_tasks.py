from allura.lib.utils import task, event_listeners

@task
def event(event_type, **kwargs):
    for e in event_listeners(event_type):
        e(**kwargs)
