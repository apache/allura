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

    # consider checking return value
    def run(self, output_consumer=None, cwd=None):
        if cwd is None:
            cwd=self.cwd()
        log.info('Running command: %r in %s', self.args, cwd)
        self.sp = subprocess.Popen(
            self.args, executable=self.args[0],
            stdin=None, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.cwd())
        if output_consumer is None:
            self.output = self.sp.stdout.read()
        else:
            output_consumer(self.sp.stdout)

        # Python docs say: Warning: This will deadlock if the child process
        # generates enough output to a stdout or stderr pipe such that it
        # blocks waiting for the OS pipe buffer to accept more data. Use
        # communicate() to avoid that.
        self.sp.wait()

        log.info('command result: %s', self.sp.returncode)
        return self.sp.returncode

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

