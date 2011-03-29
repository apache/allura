def call_wsgi_application(application, environ, catch_exc_info=False):
    """
    Call the given WSGI application, returning ``(status_string,
    headerlist, app_iter)``

    Be sure to call ``app_iter.close()`` if it's there.

    If catch_exc_info is true, then returns ``(status_string,
    headerlist, app_iter, exc_info)``, where the fourth item may
    be None, but won't be if there was an exception.  If you don't
    do this and there was an exception, the exception will be
    raised directly.
    """
    captured = []
    output = []
    def start_response(status, headers, exc_info=None):
        if exc_info is not None and not catch_exc_info:
            raise exc_info[0], exc_info[1], exc_info[2]
        captured[:] = [status, headers, exc_info]
        return output.append
    app_iter = application(environ, start_response)
    if not captured or output:
        try:
            output.extend(app_iter)
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()
        app_iter = output
    if catch_exc_info:
        return (captured[0], captured[1], app_iter, captured[2])
    else:
        return (captured[0], captured[1], app_iter)
