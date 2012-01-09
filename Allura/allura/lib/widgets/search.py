import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw

class SearchResults(ew_core.Widget):
    template='jinja:allura:templates/widgets/search_results.html'
    defaults=dict(
        ew_core.Widget.defaults,
        results=None,
        limit=None,
        page=0,
        count=0)

    class fields(ew_core.NameList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()

    def resources(self):
        for f in self.fields:
            for r in f.resources():
                yield r
