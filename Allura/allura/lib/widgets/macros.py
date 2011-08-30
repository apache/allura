import ew

class Include(ew.Widget):
    template='jinja:allura:templates/widgets/include.html'
    params=['artifact', 'attrs']
    artifact=None
    attrs = {
        'style':'width:270px;float:right;background-color:#ccc'
        }

class DownloadButton(ew.Widget):
    template='jinja:allura:templates/widgets/download_button.html'
    params=['project']
    project=None

    def resources(self):
        yield ew.jinja2_ew.JSScript('''
            $(function(){$(".download-button-%s").load("%s");
        });''' % (self.project.shortname,self.project.best_download_url()))
