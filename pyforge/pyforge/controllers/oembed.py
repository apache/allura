from __future__ import absolute_import

import os
import logging
import oembed
import mimetypes
from pprint import pformat

import pkg_resources
from tg import expose, redirect, flash, config
from tg.decorators import override_template
from webob import exc
from pylons import c, g

from pyforge.lib.base import BaseController
from pyforge.lib.dispatch import _dispatch, default

log = logging.getLogger(__name__)

class OEmbedController(BaseController):
    '''Controller that serves up oembedded resources'''

    @expose('pyforge.templates.oembed.generic')
    def index(self, href):
        try:
            response = g.oembed_consumer.embed(href)
        except oembed.OEmbedNoEndpoint:
            return dict(href=href)
        data = response.getData()
        log.info('Got response:\n%s', pformat(data))
        if isinstance(response, oembed.OEmbedPhotoResponse):
            override_template(self.index, 'genshi:pyforge.templates.oembed.photo')
        elif isinstance(response, oembed.OEmbedVideoResponse):
            override_template(self.index, 'genshi:pyforge.templates.oembed.html_tpl')
        elif isinstance(response, oembed.OEmbedRichResponse):
            override_template(self.index, 'genshi:pyforge.templates.oembed.html_tpl')
        elif isinstance(response, oembed.OEmbedLinkResponse):
            if data['provider_name'] == 'Twitter Status':
                override_template(self.index, 'genshi:pyforge.templates.oembed.link_twitter')
            elif data['provider_name'] == 'My Opera Community':
                override_template(self.index, 'genshi:pyforge.templates.oembed.link_opera')
            else: # pragma no cover
                override_template(self.index, 'genshi:pyforge.templates.oembed.link')
        else:
                pass
        return dict(href=href, data=data)

