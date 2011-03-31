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
        if len(exceptions) == 1:
            raise exceptions[0][0], exceptions[0][1], exceptions[0][2]
        else:
            raise CompoundError(*exceptions)

