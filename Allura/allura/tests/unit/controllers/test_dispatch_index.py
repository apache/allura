from mock import Mock
from allura.controllers.base import DispatchIndex, BaseController


def test_dispatch_index():
    controller = Mock(BaseController)
    d = DispatchIndex()
    d._lookup = lambda self, *remainder: (controller, remainder)

    d.dispatcher = Mock()
    state = Mock()
    d._dispatch(state, ['index'])
    state.add_controller.assert_called_with('BaseController', controller)
    d.dispatcher._dispatch.assert_called_with(state, ())

    state = Mock()
    d._dispatch(state, ['index', 'next'])
    state.add_controller.assert_called_with('BaseController', controller)
    d.dispatcher._dispatch.assert_called_with(state, ('next', ))

    state = Mock()
    d._dispatch(state, ['index2'])
    assert not state.add_controller.called
    d.dispatcher._dispatch.assert_called_with(state, ['index2'])
