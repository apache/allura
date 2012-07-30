# -*- coding: utf-8 -*-

from mock import Mock, patch, MagicMock
from ming.orm.ormsession import session
from nose.tools import assert_equal

from allura.lib import helpers as h
from allura.model import User
from pylons import c
from forgetracker.tests.unit import TrackerTestWithModel
from forgetracker.model import Ticket, Globals
from forgetracker.tracker_main import MilestoneController


def test_unicode_lookup():
    # can't use name= in constructor, that's special attribute for Mock
    milestone = Mock()
    milestone.name = u'Перспектива'
    milestone_field = Mock(milestones=[milestone])
    milestone_field.name = '_milestone'

    app = Mock(globals=Mock(milestone_fields=[milestone_field]))

    with h.push_config(c, app=app):
        root = None
        field = 'milestone'
        milestone_urlparam = '%D0%9F%D0%B5%D1%80%D1%81%D0%BF%D0%B5%D0%BA%D1%82%D0%B8%D0%B2%D0%B0' # u'Перспектива'
        mc = MilestoneController(root, field, milestone_urlparam)

    assert mc.milestone  # check that it is found
    assert_equal(mc.milestone.name, u'Перспектива')
