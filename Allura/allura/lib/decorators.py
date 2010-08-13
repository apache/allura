import sys
import json
import logging
from urllib import unquote

import webob

class ConsumerDecoration(object):

    def __init__(self, func):
        self.func = func
        self.audit_keys = set()
        self.react_keys = set()

    @classmethod
    def get_decoration(cls, func, create=True):
        if create and not hasattr(func, 'consumer_decoration'):
            func.consumer_decoration = cls(func)
        return getattr(func, 'consumer_decoration', None)

class audit(object):

    def __init__(self, *binding_keys):
        self.binding_keys = binding_keys

    def __call__(self, func):
        deco = ConsumerDecoration.get_decoration(func)
        for bk in self.binding_keys:
            deco.audit_keys.add(bk)
        return func

class react(object):

    def __init__(self, *binding_keys):
        self.binding_keys = binding_keys

    def __call__(self, func):
        deco = ConsumerDecoration.get_decoration(func)
        for bk in self.binding_keys:
            deco.react_keys.add(bk)
        return func
        
class log_action(object):

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
            except webob.exc.HTTPServerError:
                raise
            except webob.exc.HTTPException, exc:
                result = exc
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
        from pylons import request
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
