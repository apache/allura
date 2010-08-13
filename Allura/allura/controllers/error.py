# -*- coding: utf-8 -*-
"""Error controller"""

from tg import request, expose

__all__ = ['ErrorController']


class ErrorController(object):

    @expose('allura.templates.error')
    def document(self, *args, **kwargs):
        """Render the error document"""
        resp = request.environ.get('pylons.original_response')
        default_message = ("<p>We're sorry but we weren't able to process "
                           " this request.</p>")
        message = request.environ.get('error_message', default_message)
        message += '<pre>%r</pre>' % resp
        return dict(code=resp.status_int, message=message)
