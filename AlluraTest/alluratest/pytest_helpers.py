
IS_NOSE = None


def is_called_by_nose():
    global IS_NOSE
    if IS_NOSE is None:
        import inspect
        stack = inspect.stack()
        IS_NOSE = any(x[0].f_globals['__name__'].startswith('nose.') for x in stack)
    return IS_NOSE


def with_nose_compatibility(test_class):

    if not is_called_by_nose():
        return test_class

    def setUp_(self):
        setup_method = hasattr(self, 'setup_method')
        if setup_method:
            self.setup_method(None)
    if hasattr(test_class, 'setup_method'):
        test_class.setUp = setUp_

    def tearDown_(self):
        teardown_method = hasattr(self, 'teardown_method')
        if teardown_method:
            self.teardown_method(None)
    if hasattr(test_class, 'teardown_method'):
        test_class.tearDown = tearDown_

    @classmethod
    def setUpClass_(cls):
        setup_class = hasattr(cls, 'setup_class')
        if setup_class:
            cls.setup_class()
    if hasattr(test_class, 'setup_class'):
        test_class.setUpClass = setUpClass_

    @classmethod
    def tearDownClass_(cls):
        teardown_class = hasattr(cls, 'teardown_class')
        if teardown_class:
            cls.teardown_class()
    if hasattr(test_class, 'teardown_class'):
        test_class.tearDownClass = tearDownClass_

    return test_class
