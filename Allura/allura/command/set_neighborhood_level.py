from . import base

from bson import ObjectId
from allura import model as M
from allura.lib import plugin
from ming.orm import session

# Example usage:
# paster set-neighborhood-level development.ini 4f50c898610b270c92000286 silver
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
        if n_level not in ["silver", "gold", "platinum"]:
            base.log.error("You must select one of three level types (silver, gold, or platinum)")
            return
        n = M.Neighborhood.query.get(_id = ObjectId(n_id))
        n.level = n_level
        session(M.Neighborhood).flush()
