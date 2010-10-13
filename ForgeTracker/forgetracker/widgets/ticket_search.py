import ew
from allura.lib.widgets import form_fields as ffw

class TicketSearchResults(ew.SimpleForm):
    template='jinja:tracker_widgets/ticket_search_results.html'
    params=['solr_error','count','limit','query','tickets','sortable_custom_fields','sort','page']
    solr_error=None
    count=None
    limit=None
    query=None
    tickets=None
    sortable_custom_fields=None
    page=1
    sort=None

    class fields(ew.WidgetsList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()

    def resources(self):
        yield ew.resource.JSLink('tracker_js/ticket-list.js')
        for r in ffw.PageList().resources(): yield r
        for r in ffw.PageSize().resources(): yield r

class MassEdit(ew.Widget):
    template='jinja:tracker_widgets/mass_edit.html'
    params=['count','limit','query','tickets','sort','page']
    count=None
    limit=None
    query=None
    tickets=None
    page=1
    sort=None

    def resources(self):
        yield ew.resource.JSLink('tracker_js/ticket-list.js')

class MassEditForm(ew.Widget):
    template='jinja:tracker_widgets/mass_edit_form.html'
    params=['globals','query']
    globals=None
    query=None

    def resources(self):
        yield ew.resource.JSLink('tracker_js/mass-edit.js')
