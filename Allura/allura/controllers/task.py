class TaskController(object):
    '''WSGI app providing web-like RPC

    The purpose of this app is to allow us to replicate the
    normal web request environment as closely as possible
    when executing celery tasks.
    '''

    def __call__(self, environ, start_response):
        task = environ['task']
        result = task(restore_context=False)
        start_response('200 OK', [])
        return [ result ]
