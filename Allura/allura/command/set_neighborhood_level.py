from . import base

from allura import model as M
from allura.lib import plugin
from ming.orm import session

class SetNeighborhoodLevelCommand(base.Command):
    min_args=3
    max_args=3
    usage = '<ini file> <neighborhood_id> <level>'  #not sure if we need ini file
    summary = 'Change neighborhood level'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        n_id = self.args[1]
        n_level = self.args[2]
        n = M.Neighborhood.query.get(id = n_id)
        n.level = n_level
        session.commit()
