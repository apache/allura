from unittest import TestCase

from mock import patch

from allura.lib.decorators import task


class TestTask(TestCase):

    def test_no_params(self):
        @task
        def func():
            pass
        self.assertTrue(hasattr(func, 'post'))

    def test_with_params(self):
        @task(disable_notifications=True)
        def func():
            pass
        self.assertTrue(hasattr(func, 'post'))

    @patch('allura.lib.decorators.c')
    @patch('allura.model.MonQTask')
    def test_post(self, c, MonQTask):
        @task(disable_notifications=True)
        def func(s, foo=None, **kw):
            pass
        def mock_post(f, args, kw, delay=None):
            self.assertTrue(c.project.notifications_disabled)
            self.assertFalse('delay' in kw)
            self.assertEqual(delay, 1)
            self.assertEqual(kw, dict(foo=2))
            self.assertEqual(args, ('test',))
            self.assertEqual(f, func)

        c.project.notifications_disabled = False
        MonQTask.post.side_effect = mock_post
        func.post('test', foo=2, delay=1)
