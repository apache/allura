import argparse
import copy_reg
import logging
import pickle
import types

from allura.lib.decorators import task


log = logging.getLogger(__name__)


def reduce_method(m):
    return (getattr, (m.__self__, m.__func__.__name__))
copy_reg.pickle(types.MethodType, reduce_method)


@task
def dispatcher(pickled_method, *args, **kw):
    method = pickle.loads(pickled_method)
    return method(*args, **kw)


class ScriptTask(object):
    @classmethod
    def _execute(cls, arg_string):
        options = cls.parser().parse_args(arg_string.split(' '))
        cls.execute(options)

    @classmethod
    def execute(cls, options):
        """User code goes here."""
        pass

    @classmethod
    def parser(cls):
        """Return an argument parser appropriate for your script."""
        return argparse.ArgumentParser(description="Default no-op parser")

    @classmethod
    def post(cls, arg_string=''):
        pickled_method = pickle.dumps(cls._execute)
        return dispatcher.post(pickled_method, arg_string)

    @classmethod
    def main(cls):
        options = cls.parser().parse_args()
        cls.execute(options)
