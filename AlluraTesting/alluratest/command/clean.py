import os
import pkg_resources

import base
from allura.command import base as allura_base

class CleanSampleData(base.TestingCommand):
    summary = 'Clean sample data folder'
    parser = base.TestingCommand.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()

        samples_dir = pkg_resources.resource_filename(
           'alluratest', 'data')
        for fname in os.listdir(samples_dir):
            fpath = os.path.join(samples_dir, fname)
            if os.path.isfile(fpath):
                os.unlink(fpath)
