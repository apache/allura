from . import base

from allura import model as M
from allura.lib import plugin

class CreateNeighborhoodCommand(base.Command):
    min_args=3
    max_args=None
    usage = '<ini file> <neighborhood_shortname> <admin1> [<admin2>...]'
    summary = 'Create a new neighborhood with the listed admins'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        admins = [ M.User.by_username(un) for un in self.args[2:] ]
        shortname = self.args[1]
        n = M.Neighborhood(
            name=shortname,
            url_prefix='/' + shortname + '/',
            features=dict(private_projects = False,
                          max_projects = 500,
                          css = 'none',
                          google_analytics = False))
        project_reg = plugin.ProjectRegistrationProvider.get()
        project_reg.register_neighborhood_project(n, admins)
