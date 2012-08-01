import ew as ew_core
import ew.jinja2_ew as ew


class VoteForm(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/vote.html'
    defaults = dict(
        ew_core.Widget.defaults,
        action='vote',
        artifact=None
    )

    def resources(self):
        yield ew.JSLink('js/vote.js')
