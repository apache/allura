from mock import Mock

from pyforge.app import Application
from pyforge import model
from pyforge.websetup.bootstrap import wipe_database

from pyforge.tests.unit import ForgeTestWithModel


def setUp():
    wipe_database()


class TestInstall(ForgeTestWithModel):
    def test_that_it_creates_a_discussion(self):
        original_discussion_count = self.discussion_count()
        install_app()
        assert self.discussion_count() == original_discussion_count + 1

    def discussion_count(self):
        return model.Discussion.query.find().count()


class TestDefaultDiscussion(ForgeTestWithModel):
    def setUp(self):
        super(TestDefaultDiscussion, self).setUp()
        install_app()
        self.discussion = model.Discussion.query.get(shortname='myproject')

    def test_that_it_has_a_description(self):
        assert self.discussion.description == 'Forum for myproject comments'

    def test_that_it_has_a_name(self):
        assert self.discussion.name == 'myproject Discussion'

    def test_that_its_shortname_is_taken_from_the_project(self):
        assert self.discussion.shortname == 'myproject'


def install_app():
    project = Mock()
    config = Mock()
    config.options.mount_point = 'myproject'
    # XXX: Remove project argument to install; it's redundant
    Application(project, config).install(project)

