import logging

from allura.lib.decorators import exceptionless

log = logging.getLogger(__name__)


class SpamFilter(object):
    """Defines the spam checker interface and provides a default no-op impl."""
    def __init__(self, config):
        pass

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        """Return True if ``text`` is spam, else False."""
        log.info("No spam checking enabled")
        return False

    @classmethod
    def get(cls, config, entry_points):
        """Return an instance of the SpamFilter impl specified in ``config``.
        """
        method = config.get('spam.method')
        if not method:
            return cls(config)
        result = entry_points[method]
        filter_obj = result(config)
        filter_obj.check = exceptionless(False, log=log)(filter_obj.check)
        return filter_obj
