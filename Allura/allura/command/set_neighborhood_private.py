from . import base

from bson import ObjectId
from allura import model as M
from allura.lib import plugin, exceptions
from ming.orm import session


# Example usage:
# paster set-neighborhood-private development.ini <neighborhood_id> 1
class SetNeighborhoodPrivateCommand(base.Command):
    min_args = 3
    max_args = 3
    usage = '<ini file> <neighborhood_id> <private(1|0)>'
    summary = 'Set neighborhood private projects availability'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        n_id = self.args[1]
        private_val = int(self.args[2])
        if private_val == 1:
            private_val = True
        else:
            private_val = False

        n = M.Neighborhood.query.get(name=n_id)
        if not n:
            n = M.Neighborhood.query.get(_id=ObjectId(n_id))

        if not n:
            raise exceptions.NoSuchNeighborhoodError("The neighborhood %s "\
                "could not be found in the database" % n_id)
        else:
            n.allow_private = private_val
            session(M.Neighborhood).flush()
