import ew.jinja2_ew as ew
from allura.lib.widgets import form_fields as ffw

class CreatePageWidget(ffw.Lightbox):

    def resources(self):
        for r in super(CreatePageWidget, self).resources(): yield r
        yield ew.JSScript('''$(function () {
            $('#lightbox_create_wiki_page form').submit(function(){
                location.href=$('#sidebar a.add_wiki_page').attr('href')+encodeURIComponent($('input[name=name]', $(this)).val())+'/edit';
                return false;
            });
        });''');