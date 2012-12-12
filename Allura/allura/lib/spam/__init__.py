class FakeSpamChecker(object):
    """No-op spam checker"""
    def check(self, *args, **kw):
        return False
