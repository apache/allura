from __future__ import with_statement
import logging
import os.path
from itertools import chain, groupby
from mimetypes import guess_type
from collections import defaultdict
from urllib import urlencode

import pkg_resources
import slimmer
from pylons import c, request
from tg import expose, response, controllers, validate
from webob import exc
from formencode.validators import UnicodeString
from formencode.foreach import ForEach

from .core import Widget, ControllerWidget, WidgetInstance

log = logging.getLogger(__name__)

class ResourceManager(object):
    location = [ 'head_css', 'head_js',
                 'body_top_js', 'body_js' ]
    block_size = 4096
    paths = []
    kwargs = {}

    @classmethod
    def configure(cls, **kw):
        cls.kwargs = kw

    @classmethod
    def get(cls, **kw):
        if not getattr(c, '_ew_resources', None):
            c._ew_resources = cls(**cls.kwargs)
        return c._ew_resources

    @classmethod
    def register_directory(cls, url_path, directory):
        for up,dir in cls.paths:
            if up == url_path: return
        cls.paths.append((url_path, directory))

    @classmethod
    def register_all_resources(cls):
        for ep in pkg_resources.iter_entry_points('easy_widgets.resources'):
            log.info('Loading ep %s', ep)
            ep.load()(cls)

    def __init__(self, script_name='/_ew_resources/', compress=False):
        self.resources = defaultdict(list)
        self.script_name = script_name
        self.compress = compress
        self._slim = SlimmerController(self)

    def emit(self, location):
        def squash_dupes(it):
            seen = set()
            for r in it:
                if r.squash and r in seen: continue
                yield r
        def compress(it):
            for (cls, compress), rs in groupby(it, key=lambda r:(type(r), r.compress)):
                if not compress:
                    for r in rs: yield r
                else:
                    for cr in cls.compressed(self, rs):
                        yield cr
        resources = self.resources[location]
        resources = squash_dupes(resources)
        if self.compress:
            resources = compress(resources)
        for r in resources:
            yield r.display()
            yield '\n'

    def register_widgets(self, context):
        for name in dir(context):
            w = getattr(context, name)
            if isinstance(w, (Widget, WidgetInstance, Resource)):
                log.debug('Registering resources for %s', w)
                self.register(w)

    def register(self, resource):
        if isinstance(resource, Resource):
            assert resource.location in self.location, \
                'Resource.location must be one of %r' % self.location
            self.resources[resource.location].append(resource)
            resource.manager = self
        elif isinstance(resource, Widget):
            for r in resource.resources(): self.register(r)
        elif isinstance(resource, WidgetInstance):
            for r in resource.widget_type.resources(): self.register(r)
        else:
            raise AssertionError, 'Unknown resource type %r' % resource

    @expose(content_type=controllers.CUSTOM_CONTENT_TYPE)
    def _default(self, *args, **kwargs):
        res_path = request.path_info[len(self.script_name):]
        fs_path = self.get_filename(res_path)
        if fs_path is None:
            log.warning('Could not map %s', res_path)
            log.info('Mapped directories: %r', self.paths)
            raise exc.HTTPNotFound(res_path)
        file_iter = self._serve_file(fs_path, res_path)
        # Make sure 404s are raised appropriately
        return chain([ file_iter.next() ], file_iter)
    default=_default

    def get_filename(self, res_path):
        for url_path, directory in self.paths:
            if res_path.startswith(url_path):
                fs_path = os.path.join(
                    directory,
                    res_path[len(url_path)+1:])
                if not fs_path.startswith(directory):
                    return None
                return fs_path
        return None

    def _serve_file(self, fs_path, res_path):
        try:
            response.headers['Content-Type'] = ''
            content_type = guess_type(fs_path)
            if content_type: content_type = content_type[0]
            else: content_type = 'application/octet-stream'
            response.content_type = content_type
        except TypeError:
            log.error('Error in _Serve_file')
        try:
            with open(fs_path, 'rb') as fp:
                while True:
                    buffer = fp.read(self.block_size)
                    if not buffer: break
                    yield buffer
        except IOError:
            log.warning('Could not find %s', res_path)
            raise exc.HTTPNotFound(res_path)

    def __repr__(self):
        l = ['<ResourceManager>']
        for name, res in self.resources.iteritems():
            l.append('  <Location %s>' % name)
            for r in res: l.append('    %r' % r)
        for u,d in self.paths:
            l.append('  <Path url="%s" directory="%s">' % (u, d))
        return '\n'.join(l)

class SlimmerController(object):
    resource_cache = {}

    def __init__(self, rm, use_cache=True):
        self.rm = rm
        self.use_cache = use_cache

    @expose(content_type=controllers.CUSTOM_CONTENT_TYPE)
    def js(self, href):
        response.headers['Content-Type'] = 'text/javascript'
        return self._serve('js', href)

    @expose(content_type=controllers.CUSTOM_CONTENT_TYPE)
    def css(self, href):
        response.headers['Content-Type'] = 'text/css'
        return self._serve('css', href)

    def _serve(self, file_type, href):
        try:
            return self.resource_cache[href]
        except KeyError:
            pass
        content = '\n'.join(
            open(self.rm.get_filename(h)).read()
            for h in href.split(';'))
        content = slimmer.slimmer(content, file_type)
        if self.use_cache:
            self.resource_cache[href] = content
        return content

class ResourceHolder(Widget):

    def __init__(self, *resources):
        self._resources = resources

    def resources(self):
        return self._resources

class Resource(object):

    def __init__(self, location, widget, context, squash=True, compress=True):
        self.location = location
        self.widget = widget
        self.context = context
        self.squash = squash
        self.compress = compress
        self.manager = None

    def display(self):
        wi = WidgetInstance(self.widget, self.context)
        return wi.display()

    @classmethod
    def compressed(cls, manager, resources):
        return resources

class ResourceLink(Resource):
    file_type=None

    def __init__(self, url, location, squash, compress):
        self._url = url
        super(ResourceLink, self).__init__(
            location, ControllerWidget(self.index), {}, squash, compress)

    def url(self):
        if '//' not in self._url and not self._url.startswith('/'):
            return self.manager.script_name + self._url
        return self._url

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self._url)

    def __hash__(self):
        return hash(self.location) + hash(self._url) + hash(self.squash)

    def __eq__(self, o):
        return (self.__class__ == o.__class__
                and self._url == o._url
                and self.location == o.location
                and self.squash == o.squash)

    @classmethod
    def compressed(cls, manager, resources):
        rel_hrefs = [ r.url()[len(manager.script_name):]
                      for r in resources ]
        query = urlencode([('href', ';'.join(rel_hrefs))])
        result = cls('%s_slim/%s?%s' % (
                manager.script_name,
                cls.file_type,
                query))
        yield result

class JSLink(ResourceLink):
    file_type='js'

    def __init__(self, url, location='body_js', squash=True, compress=True):
        super(JSLink, self).__init__(url, location, squash, compress)

    @expose('genshi:ew.templates.jslink')
    def index(self, **kwargs):
        return dict(href=self.url())

class CSSLink(ResourceLink):
    file_type='css'

    def __init__(self, url, squash=True, compress=True, **attrs):
        self.attrs = attrs
        super(CSSLink, self).__init__(url, 'head_css', squash, compress)

    @expose('genshi:ew.templates.csslink')
    def index(self, **kwargs):
        return dict(href=self.url(), attrs=self.attrs)

class ResourceScript(Resource):
    file_type=None

    def __init__(self, text, location, squash, compress):
        self.text = text
        super(ResourceScript, self).__init__(
            location, ControllerWidget(self.index), {}, squash, compress)

    def __hash__(self):
        return (hash(self.text)
                + hash(self.location)
                + hash(self.squash)
                + hash(self.compress))

    def __eq__(self, o):
        return (self.__class__ == o.__class__
                and self.text == o.text
                and self.location == o.location
                and self.squash == o.squash
                and self.compress == o.compress)

    @classmethod
    def compressed(cls, manager, resources):
        text = '\n'.join(r.text for r in resources)
        slim_text = slimmer.slimmer(text, cls.file_type)
        result = cls(slim_text)
        yield result

class JSScript(ResourceScript):
    file_type='js'

    def __init__(self, text, location='body_js', squash=True, compress=True):
        super(JSScript, self).__init__(text, location, squash, compress)

    @expose('genshi:ew.templates.jsscript')
    def index(self, **kwargs):
        return dict(text=self.text)

class CSSScript(ResourceScript):
    file_type='css'

    def __init__(self, text):
        super(CSSScript, self).__init__(text, 'head_css', True, True)

    @expose('genshi:ew.templates.cssscript')
    def index(self, **kwargs):
        return dict(text=self.text)

class GoogleAnalytics(Resource):

    def __init__(self, account):
        self.account = account
        super(GoogleAnalytics, self).__init__(
            'head_js', ControllerWidget(self.index), {}, True)

    @expose('genshi:ew.templates.google_analytics')
    def index(self, **kwargs):
        return dict(account=self.account)

