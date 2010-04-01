from pylons import c
from pyforge.model import User

import ew

class ProjectSummary(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.project_summary'
    params=['value']
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tools.min.js')
        # yield ew.JSScript('''
        # (function(){
        # })();
        # ''')