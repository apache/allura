import ew

class SVNRevisionWidget(ew.Widget):
    template='jinja:svn_widgets/revision.html'
    params=['value', 'prev', 'next']
    value=None
    prev=next=None
