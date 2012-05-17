from . import base

from ming.orm import session

from allura import model as M
from allura.lib import plugin, exceptions

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
            home_tool_active=False,
            features=dict(private_projects = False,
                          max_projects = 500,
                          css = 'none',
                          google_analytics = False))
        project_reg = plugin.ProjectRegistrationProvider.get()
        project_reg.register_neighborhood_project(n, admins)
        print "WARNING! You must restart the webserver before you can use the new neighborhood."


class UpdateNeighborhoodCommand(base.Command):
    min_args=3
    max_args=None
    usage = '<ini file> <neighborhood_shortname> <home_tool_active>'
    summary = 'Activate Home application for neighborhood'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        shortname = self.args[1]
        nb = M.Neighborhood.query.get(name=shortname)
        if nb is None:
            raise exceptions.NoSuchNeighborhoodError("The neighborhood %s " \
                "could not be found in the database" % shortname)
        tool_value = self.args[2].lower()
        if tool_value[:1] == "t":
            home_tool_active = True
        else:
            home_tool_active = False
        nb.home_tool_active = home_tool_active
        session(M.Neighborhood).flush()
