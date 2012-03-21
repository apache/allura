from allura.command import base

from bson import ObjectId
from allura import model as M
from allura.lib import plugin, exceptions
from ming.orm import session


# Example usage:
# paster set-neighborhood-level development.ini 4f50c898610b270c92000286 silver
class SetNeighborhoodLevelCommand(base.Command):
    min_args = 3
    max_args = 3
    usage = "<ini file> <neighborhood> <level>"  # not sure if we need ini file
    summary = "Change the neighborhood level\r\n" \
        "\t<neighgborhood> - the neightborhood name or object id\r\n" \
        "\t<level> - silver, gold or platinum"
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        n_id = self.args[1]
        n_level = self.args[2]
        if n_level not in ["silver", "gold", "platinum"]:
            raise exceptions.NoSuchNBLevelError("%s is not a valid " \
                "neighborhood level. The valid levels are \"silver\", " \
                "\"gold\" and \"platinum\"" % n_level)

        n = M.Neighborhood.query.get(name=n_id)
        if not n:
            n = M.Neighborhood.query.get(_id=ObjectId(n_id))

        if not n:
            raise exceptions.NoSuchNeighborhoodError("The neighborhood %s " \
                "could not be found in the database" % n_id)
        else:
            n.level = n_level
            if n_level == "gold":
                n.migrate_css_for_gold_level()
            session(M.Neighborhood).flush()
