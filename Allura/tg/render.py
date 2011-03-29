import pkg_resources

import jinja2
from webhelpers.html import literal

import ew

class JinjaEngine(ew.TemplateEngine):

    def __init__(self, ep, config):
        self._ep = ep
        self._environ = None

    @property
    def environ(self):
        if self._environ is None:
            self._environ = jinja2.Environment(
            loader=PackagePathLoader(),
            auto_reload=True,
            autoescape=True,
            extensions=['jinja2.ext.do'])
        return self._environ

    def load(self, template_name):
        try:
            return self.environ.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise ew.errors.TemplateNotFound, '%s not found' % template_name

    def parse(self, template_text, filepath=None):
        return self.environ.from_string(template_text)

    def render(self, template, context):
        context = self.context(context)
        with ew.utils.push_context(ew.widget_context, render_context=context):
            text = template.render(**context)
            return literal(text)

class PackagePathLoader(jinja2.BaseLoader):

    def __init__(self):
        self.fs_loader = jinja2.FileSystemLoader(['/'])

    def get_source(self, environment, template):
        package, path = template.split(':')
        filename = pkg_resources.resource_filename(package, path)
        return self.fs_loader.get_source(environment, filename)
