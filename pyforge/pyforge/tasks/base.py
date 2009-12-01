from pylons import g

import celery.task
from celery.execute import apply_async, apply

class Task(celery.task.Task):

    @classmethod
    def delay(cls, *args, **kwargs):
        if g.use_queue:
            return apply_async(cls, args, kwargs)
        else:
            return apply(cls, args, kwargs)

