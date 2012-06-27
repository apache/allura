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
            features=dict(private_projects = False,
                          max_projects = 500,
                          css = 'none',
                          google_analytics = False))
        project_reg = plugin.ProjectRegistrationProvider.get()
        project_reg.register_neighborhood_project(n, admins)


class UpdateNeighborhoodCommand(base.Command):
    min_args=3
    max_args=None
    usage = '<ini file> <neighborhood_shortname> <home_tool_active>'
    summary = 'Activate Home application for neighborhood\r\n' \
        '\t<neighborhood> - the neighborhood name\r\n' \
        '\t<value> - boolean value to install/uninstall Home tool\r\n' \
        '\t    must be True or False\r\n\r\n' \
        '\tExample:\r\n' \
        '\tpaster update-neighborhood-home-tool development.ini Projects True'
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

        if home_tool_active == nb.has_home_tool:
            return

        p = nb.neighborhood_project
        if home_tool_active:
            zero_position_exists = False
            for ac in p.app_configs:
                if ac.options['ordinal'] == 0:
                    zero_position_exists = True
                    break

            if zero_position_exists:
                for ac in p.app_configs:
                    ac.options['ordinal'] = ac.options['ordinal'] + 1
            p.install_app('home', 'home', 'Home', ordinal=0)
        else:
            app_config = p.app_config('home')
            zero_position_exists = False
            if app_config.options['ordinal'] == 0:
                zero_position_exists = True

            p.uninstall_app('home')
            if zero_position_exists:
                for ac in p.app_configs:
                    ac.options['ordinal'] = ac.options['ordinal'] - 1

        session(M.AppConfig).flush()
        session(M.Neighborhood).flush()
