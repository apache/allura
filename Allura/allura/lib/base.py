# -*- coding: utf-8 -*-
"""The base Controller API."""
from webob import exc
from tg import TGController, config

__all__ = ['WsgiDispatchController']

class WsgiDispatchController(TGController):
    """
    Base class for the controllers in the application.

    Your web application should have one of these. The root of
    your application is used to compute URLs used by your app.

    """

    def _setup_request(self):
        '''Responsible for setting all the values we need to be set on pylons.c'''
        raise NotImplementedError, '_setup_request'

    def _cleanup_request(self):
        raise NotImplementedError, '_cleanup_request'

    def __call__(self, environ, start_response):
        host = environ['HTTP_HOST'].lower()
        if host == config['oembed.host']:
            from allura.controllers.oembed import OEmbedController
            return OEmbedController()(environ, start_response)
        try:
            self._setup_request()
            response = super(WsgiDispatchController, self).__call__(environ, start_response)
            return self.cleanup_iterator(response)
        except exc.HTTPException, err:
            return err(environ, start_response)

    def cleanup_iterator(self, response):
        for chunk in response: yield chunk
        self._cleanup_request()


