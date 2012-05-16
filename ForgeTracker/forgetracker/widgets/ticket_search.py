import tg

from pylons import c

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets import form_fields as ffw

class TicketSearchResults(ew_core.SimpleForm):
    template='jinja:forgetracker:templates/tracker_widgets/ticket_search_results.html'
    defaults=dict(
        ew_core.SimpleForm.defaults,
        solr_error=None,
        count=None,
        limit=None,
        query=None,
        tickets=None,
        sortable_custom_fields=None,
        page=1,
        sort=None,
        columns=None)

    class fields(ew_core.NameList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()
        lightbox=ffw.Lightbox(name='col_list',trigger='#col_menu')

    def resources(self):
        yield ew.JSLink('tracker_js/ticket-list.js')
        yield ew.CSSLink('tracker_css/ticket-list.css')
        for r in super(TicketSearchResults, self).resources():
            yield r

class MassEdit(ew_core.SimpleForm):
    template='jinja:forgetracker:templates/tracker_widgets/mass_edit.html'
    defaults=dict(
        ew_core.SimpleForm.defaults,
        count=None,
        limit=None,
        query=None,
        tickets=None,
        page=1,
        sort=None)

    class fields(ew_core.NameList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()
        lightbox=ffw.Lightbox(name='col_list',trigger='#col_menu')

    def resources(self):
        yield ew.JSLink('tracker_js/ticket-list.js')
        yield ew.CSSLink('tracker_css/ticket-list.css')
        for r in super(MassEdit, self).resources():
            yield r

class MassEditForm(ew_core.Widget):
    template='jinja:forgetracker:templates/tracker_widgets/mass_edit_form.html'
    defaults=dict(
        ew_core.Widget.defaults,
        globals=None,
        query=None,
        cancel_href=None,
        limit=None,
        sort=None)

    def resources(self):
        yield ew.JSLink('tracker_js/mass-edit.js')

class SearchHelp(ffw.Lightbox):
    defaults=dict(
        ffw.Lightbox.defaults,
        name='search_help_modal',
        trigger='a.search_help_modal',
        content="""<div style="height:400px; overflow:auto;"><h1>Searching for tickets</h1>
<p>Searches use <a href="http://www.solrtutorial.com/solr-query-syntax.html" target="_blank">solr lucene query syntax</a>. Use the following fields in tracker ticket searches:</p>
<ul>
<li>User who owns the ticket - assigned_to_s</li>
<li>Labels assigned to the ticket - labels</li>
<li>Milestone the ticket is assigned to - _milestone</li>
<li>Last modified date - mod_date_dt</li>
<li>Body of the ticket - text</li>
<li>Number of ticket - ticket_num</li>
<li>User who created the ticket - reported_by_s</li>
<li>Status of the ticket - status</li>
<li>Title of the ticket - summary</li>
<li>Custom field - the field name with an underscore in front like _custom</li>
</ul>
<h2>Example searches</h2>
<p>Any ticket that is not closed in the 1.0 milestone with "foo" in the title</p>
<div class="codehilite"><pre>!status:closed and summary:foo* and _milestone:1.0</pre></div>
<p>Tickets with the label "foo" but not the label "bar":</p>
<div class="codehilite"><pre>labels:foo and -labels:bar</pre></div>
<p>Tickets assigned to or added by a user with the username "admin1" and the custom field "size" set to 2</p>
<div class="codehilite"><pre>(assigned_to_s:admin1 or reported_by_s:admin1) and _size:2</pre></div>
<p>The ticket has "foo" as the title or the body with a number lower than 50</p>
<div class="codehilite"><pre>(summary:foo or text:foo) and ticket_num:[* TO 50]</pre></div>
<p>Tickets last modified in April 2012</p>
<div class="codehilite"><pre>mod_date_dt:[2012-04-01T00:00:00Z TO 2012-04-30T23:59:59Z]</pre></div>
<h2>Saving searches</h2>
<p>Ticket searches may be saved for later use by project administrators. To save a search, click "Edit Searches" in the tracker sidebar. Click "Add Bin" then enter a summary and search terms for the saved search. Your search will now show up in the sidebar under "Searches" with a count of how many tickets match the query.</p>
<h2>Sorting search results</h2>
<p>Ticket search results can be sorted by clicking the header of the column you want to sort by. The first click will sort the results in ascending order. Clicking the header again will sort the column in descending order. In addition to sorting by the column headers, you can manually sort on these properties:</p>
<ul>
<li>Labels assigned to the ticket - labels_s</li>
<li>Milestone the ticket is assigned to - _milestone_s</li>
<li>Last modified date - mod_date_dt</li>
<li>Body of the ticket - text_s</li>
<li>Number of ticket - ticket_num_i</li>
<li>User who created the ticket - reported_by_s</li>
<li>Status of the ticket - status_s</li>
<li>Title of the ticket - snippet_s</li>
<li>Custom field - the field name with an _ in front and _s at the end like _custom_s</li>
</ul>
<p>You can use these properties by appending them to the url (only one sort allowed at a time) like this:</p>
<div class="codehilite"><pre>/p/yourproject/tickets/search/?q=_milestone:1.0&amp;sort=snippet_s+asc</pre></div></div>
""")