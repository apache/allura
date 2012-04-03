import ew as ew_core
import ew.jinja2_ew as ew

from pylons import g, c

from allura import model as M
from allura.lib.security import Credentials

class ProjectSummary(ew_core.Widget):
    template='jinja:allura:templates/widgets/project_summary.html'
    defaults=dict(
        ew_core.Widget.defaults,
        sitemap=None,
        icon=None,
        value=None,
        icon_url=None,
        accolades=None,
        columns=3,
        show_proj_icon=True,
        show_download_button=True)

    def prepare_context(self, context):
        response = super(ProjectSummary, self).prepare_context(context)
        value = response['value']
        if response['sitemap'] is None:
            response['sitemap'] = [ s for s in value.sitemap() if s.url ]
        if response['icon_url'] is None:
            if value.icon:
                response['icon_url'] = value.url()+'icon'
            else:
                response['icon_url'] = g.forge_static('images/project_default.png')
        if response['accolades'] is None:
            response['accolades'] = value.accolades

        true_list = ['true', 't', '1', 'yes', 'y']
        if type(response['show_proj_icon']) == unicode:
            if response['show_proj_icon'].lower() in true_list:
                response['show_proj_icon'] = True
            else:
                response['show_proj_icon'] = False
        if type(response['show_download_button']) == unicode:
            if response['show_download_button'].lower() in true_list:
                response['show_download_button'] = True
            else:
                response['show_download_button'] = False

        return response

    def resources(self):
        yield ew.JSLink('js/jquery.tools.min.js')
        yield ew.JSScript('''
        $(document).ready(function () {
            var badges = $('small.badge');
            var i = badges.length;
            while (i) {
                i--;
                var tipHolder = document.createElement('div');
                tipHolder.id = "tip" + i;
                tipHolder.className = "tip";
                document.body.appendChild(tipHolder);
                $(badges[i]).parent('a[title]').tooltip({
                    tip: '#tip' + i,
                    opacity: '.9',
                    offset: [-10, 0]
                });
            }
        });
        ''')

class ProjectList(ew_core.Widget):
    template='jinja:allura:templates/widgets/project_list_widget.html'
    defaults=dict(
        ew_core.Widget.defaults,
        projects=[],
        project_summary=ProjectSummary(),
        display_mode='list',
        sitemaps=None,
        icon_urls=None,
        accolades_index=None)

    def prepare_context(self, context):
        response = super(ProjectList, self).prepare_context(context)
        cred = Credentials.get()
        projects = response['projects']
        cred.load_user_roles(c.user._id, *[p._id for p in projects])
        cred.load_project_roles(*[p._id for p in projects])
        if response['sitemaps'] is None:
            response['sitemaps'] = M.Project.menus(projects)
        if response['icon_urls'] is None:
            response['icon_urls'] = M.Project.icon_urls(projects)
        if response['accolades_index'] is None:
            response['accolades_index'] = M.Project.accolades_index(projects)
        return response

    def resources(self):
        for r in self.project_summary.resources():
            yield r

class ProjectScreenshots(ew_core.Widget):
    template='jinja:allura:templates/widgets/project_screenshots.html'
    defaults=dict(
        ew_core.Widget.defaults,
        project=None,
        edit=False)
