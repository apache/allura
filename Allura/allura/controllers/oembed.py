from __future__ import absolute_import

import os
import logging
import oembed
import mimetypes
from pprint import pformat
from urllib2 import HTTPError

import pkg_resources
from tg import expose, redirect, flash, config
from tg.decorators import override_template
from webob import exc
from pylons import c, g

from allura.lib.base import BaseController

log = logging.getLogger(__name__)

class OEmbedController(BaseController):
    '''Controller that serves up oembedded resources'''

    @expose('jinja:oembed/generic.html')
    def index(self, href, **kw):
        try:
            response = g.oembed_consumer.embed(href)
        except (oembed.OEmbedNoEndpoint, HTTPError), ex:
            return dict(href=href)
        data = response.getData()
        log.info('Got response:\n%s', pformat(data))
        if isinstance(response, oembed.OEmbedPhotoResponse):
            override_template(self.index, 'jinja:oembed/photo.html')
        elif isinstance(response, oembed.OEmbedVideoResponse):
            override_template(self.index, 'jinja:oembed/html_tpl.html')
        elif isinstance(response, oembed.OEmbedRichResponse):
            override_template(self.index, 'jinja:oembed/html_tpl.html')
        elif isinstance(response, oembed.OEmbedLinkResponse):
            if data['provider_name'] == 'Twitter Status':
                override_template(self.index, 'jinja:oembed/link_twitter.html')
            elif data['provider_name'] == 'My Opera Community':
                override_template(self.index, 'jinja:oembed/link_opera.html')
            else: # pragma no cover
                override_template(self.index, 'jinja:oembed/link.html')
        else:
                pass
        return dict(href=href, data=data)

