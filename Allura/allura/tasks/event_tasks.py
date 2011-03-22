import sys

from allura.lib.decorators import task, event_handler
from allura.lib.exceptions import CompoundError

@task
def event(event_type, *args, **kwargs):
    exceptions = []
    for t in event_handler.listeners[event_type]:
        try:
            t(event_type, *args, **kwargs)
        except:
            exceptions.append(sys.exc_info())
    if exceptions:
        raise CompoundError(*exceptions)

