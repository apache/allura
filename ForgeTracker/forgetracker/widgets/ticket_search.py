import ew

class TicketSearchResults(ew.Widget):
    template='genshi:forgetracker.widgets.templates.ticket_search_results'
    params=['solr_error','count','limit','query','tickets','sortable_custom_fields','sort','page']
    solr_error=None
    count=None
    limit=None
    query=None
    tickets=None
    sortable_custom_fields=None
    page=1
    sort=None

    def resources(self):
        yield ew.resource.JSLink('tracker_js/ticket-list.js')

class MassEdit(ew.Widget):
    template='genshi:forgetracker.widgets.templates.mass_edit'
    params=['count','limit','query','tickets','sort','page','globals']
    count=None
    limit=None
    query=None
    tickets=None
    page=1
    sort=None
    globals=None

    def resources(self):
        yield ew.resource.JSLink('tracker_js/ticket-list.js')
        yield ew.resource.JSLink('tracker_js/mass-edit.js')