import warnings
from nose.plugins import Plugin

class NoWarnings(Plugin):

    def beforeTest(self, result):
        # Suppress warnings during tests to reduce noise
        warnings.simplefilter("ignore")

    def afterTest(self, result):
        # Clear list of warning filters
        warnings.resetwarnings()
