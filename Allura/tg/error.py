from paste.deploy.converters import asbool

from weberror.evalexception import EvalException
from weberror.errormiddleware import ErrorMiddleware

def ErrorHandler(app, global_conf, **errorware):
    if asbool(global_conf.get('debug')):
        app = EvalException(app, global_conf)
    else:
        app = ErrorMiddleware(app, global_conf, **errorware)
    return app
