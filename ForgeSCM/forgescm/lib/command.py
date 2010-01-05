import os
import shutil
import logging
import subprocess

from pylons import c

log = logging.getLogger(__name__)

class Command(object):
    base=None

    def __init__(self, *args):
        if isinstance(self.base, basestring):
            base = self.base.split()
        else:
            base = self.base
        self.args = tuple(base) + args

    def run(self, output_consumer=None, cwd=None):
        if cwd is None:
            cwd=self.cwd()
        self.sp = subprocess.Popen(
            self.args, executable=self.args[0],
            stdin=None, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.cwd())
        if output_consumer is None:
            self.output = self.sp.stdout.read()
        else:
            output_consumer(self.sp.stdout)
        self.sp.wait()

    def run_exc(self, *args, **kwargs):
        result = self.run(*args, **kwargs)
        assert not self.sp.returncode, self.output

    def cwd(self):
        try:
            result = c.app.repo.repo_dir
        except:
            result = os.getcwd()
            log.exception("Can't set cwd to app dir, defaulting to %s",
                          result)
        return result

    def clean_dir(self):
        path = self.cwd()
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

