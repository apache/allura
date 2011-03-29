from tg import expose, environ

class TaskController(object):
    '''WSGI app providing web-like RPC

    The purpose of this app is to allow us to replicate the
    normal web request environment as closely as possible
    when executing celery tasks.
    '''

    @expose()
    def index(self):
        task = environ['task']
        result = task(restore_context=False)
        return [ result ]

    def _lookup(self, name):
        return self
