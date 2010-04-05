from pylons import c
from pyforge.model import User

import ew

class ProjectSummary(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.project_summary'
    params=['value']
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tools.min.js')
        yield ew.JSScript('''
        $(document).ready(function() {
            var badges = $('small.badge');
            var i = badges.length;
            while(i){
		        i--;
		    var tipHolder = document.createElement('div');
		    tipHolder.id = "tip"+i;
		    tipHolder.className = "tip";
		    document.body.appendChild(tipHolder)
		    $(badges[i]).parent('a[title]').tooltip({
		        tip: '#tip'+i,
		        opacity: '.9',
		        offset: [-10,0]
		    });
            }
		});
        ''')