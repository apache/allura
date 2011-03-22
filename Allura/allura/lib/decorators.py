import sys
import json
import logging
from collections import defaultdict
from urllib import unquote
from tg.decorators import before_validate
from tg import request, redirect

from webob import exc

def task(func):
    '''Decorator to add some methods to task functions'''
    def post(*args, **kwargs):
        from allura import model as M
        return M.MonQTask.post(func, args, kwargs)
    func.post = post
    return func

class event_handler(object):
    '''Decorator to register event handlers'''
    listeners = defaultdict(set)

    def __init__(self, *topics):
        self.topics = topics

    def __call__(self, func):
        for t in self.topics:
            self.listeners[t].add(func)
        return func

class require_post(object):

    def __init__(self, redir=None):
        self.redir = redir

    def __call__(self, func):
        def check_method(remainder, params):
            if request.method != 'POST':
                if self.redir is not None:
                    redirect(self.redir)
                raise exc.HTTPMethodNotAllowed(headers={'Allow':'POST'})
        before_validate(check_method)(func)
        return func

class log_action(object): # pragma no cover

    def __init__(self,
                 logger=None,
                 level=logging.INFO,
                 msg=None,
                 *args, **kwargs):
        if logger is None: logger = logging
        self._logger = logger
        self._level = level
        self._msg = msg
        self._args = args
        self._kwargs = kwargs
        self._extra_proto = dict(
            user=None,
            user_id=None,
            source=None,
            project_name=None,
            group_id=None)

    def __call__(self, func):
        self._func = func
        self._extra_proto.update(action=func.__name__)
        if self._msg is None:
            self._msg = func.__name__
        result = lambda *args,**kwargs: self._wrapper(*args,**kwargs)
        # assert not hasattr(func, 'decoration')
        if hasattr(func, 'decoration'):
            result.decoration = func.decoration
        return result

    def _wrapper(self, *args, **kwargs):
        result = None
        try:
            try:
                result = self._func(*args, **kwargs)
            except exc.HTTPServerError:
                raise
            except exc.HTTPException, e:
                result = e
            args = self._args
            kwargs = self._kwargs
            extra = kwargs.setdefault('extra', {})
            extra.update(self._make_extra(result))
            self._logger.log(self._level, self._msg,
                             *self._args, **self._kwargs)
            return result
        except:
            args = self._args
            kwargs = self._kwargs
            extra = kwargs.setdefault('extra', {})
            extra.update(self._make_extra(result))
            kwargs['exc_info'] = sys.exc_info()
            self._logger.log(logging.ERROR, self._msg,
                             *self._args, **self._kwargs)
            raise

    def _make_extra(self, result=None):
        '''Create a dict of extra items to be added to a log record
        '''
        extra = self._extra_proto.copy()
        # Save the client IP address
        client_ip = request.headers.get('X_FORWARDED_FOR', request.remote_addr)
        client_ip = client_ip.split(',')[0].strip()
        extra.update(client_ip=client_ip)
        # Save the user info
        user = getattr(request, 'user', None)
        if user:
            extra.update(user=user.username,
                         user_id=user.id)
        # Save the project info
        if (result
            and isinstance(result, dict)
            and 'p' in result
            and result['p'] is not None):
            extra.update(
                source=result['p']['source'],
                project_name=result['p']['shortname'],
                group_id=result['p'].get('sf_id'))
        # Log the referer cookie if it exists
        referer_link = request.cookies.get('referer_link')
        if referer_link:
            referer_link = unquote(referer_link)
            try:
                referer_link = json.loads(referer_link)
            except ValueError:
                pass
        extra['referer_link'] = referer_link
        return extra

class exceptionless(object):
    '''Decorator making the decorated function return 'error_result' on any
    exceptions rather than propagating exceptions up the stack
    '''

    def __init__(self, error_result, log=None):
        self.error_result = error_result
        self.log = log

    def __call__(self, fun):
        fname = 'exceptionless(%s)' % fun.__name__
        def inner(*args, **kwargs):
            try:
                return fun(*args, **kwargs)
            except:
                if self.log:
                    self.log.exception('Error calling %s', fname)
                return self.error_result
        inner.__name__ = fname
        return inner
