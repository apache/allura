Creating your first PyForge Tool
=====================================================================

Adding your PyForge Tool to a PyForge Install
=====================================================================

Writing a Wiki Tool Part 1: Pages
=====================================================================

Writing a wiki Tool Part 2: Links
=====================================================================

Writing a wiki Tool Part 3: Revisions
=====================================================================

Testing your Tool
===========================

Testing the controllers and models of a new Forge tool is fairly
straightforward.  Generally, you should follow the example of tests in the
`pyforge/tests/functional` directory for controller tests and
`pyforge.tests.model` for model tests.  For functional tests, the Forge platform
provides a convenient "test harness" :class:`pyforge.controllers.test.TestController` controller
class which is used as the application root for the
:class:`pyforge.tests.TestController` class.

In order to test your new tool controllers, you simply need to use the `self.app.get()`
and `self.app.post()` methods of your test controller.  The test harness makes
all the tools available in the system available under the URL /*entry point
name*/.  So to test the :mod:`pyforge.ext.project_home` tool, for instance, we
need only write the following::

    from pyforge.tests import TestController

    class TestProjectHome(TestController):

        def test_home(self):
            r = self.app.get('/home/')

Whenever you use the :class:`pyforge.tests.TestController` app property, the
test harness sets up the context so that `c.project` is always the
`projects/test` project and whichever tool name you request is mounted at its
entry point (so the Wiki tool will be mounted at /Wiki/).  `c.user` is always
set to the `test_admin` user to avoid authentication issues.

The framework used to generate the WSGI environment for testing your tools is
provided by the `WebTest <http://pythonpaste.org/webtest/>`_ module, where you can
find further documentation for the `.get()` and `.post()` methods.

Testing new Forge models is also straightforward, though it usually requires
setting the pylons context object `c` before your test.  An example of this
technique follows::

    import mock
    from pylons import c, g

    from pyforge.lib.app_globals import Globals
    from pyforge import model as M

    def setUp():
        g._push_object(Globals())
        c._push_object(mock.Mock())
        g.set_project('projects/test')
        g.set_app('hello')
        c.user = M.User.query.get(username='test_admin')

Testing the reactors/auditors is similar to testing models.  Generally, you will
simply want to call your callback methods directly rather than setting up a full mocking
infrastructure for the messaging system provided by RabbitMQ.
