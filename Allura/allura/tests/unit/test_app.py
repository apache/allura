import pytest

from allura.app import Application
from allura import model
from allura.lib import helpers as h
from allura.tests.unit import WithDatabase
from allura.tests.unit.patches import fake_app_patch
from allura.tests.unit.factories import create_project, create_app_config


def test_validate_mount_point():
    app = Application

    assert app.validate_mount_point('dash-in-middle') is not None
    assert app.validate_mount_point('end-dash-') is None

    mount_point = '1.2+foo_bar'
    assert app.validate_mount_point(mount_point) is None

    with h.push_config(app, relaxed_mount_points=True):
        assert app.validate_mount_point(mount_point) is not None


def test_describe_permission():
    class DummyApp(Application):
        permissions_desc = {
            'foo': 'bar',
            'post': 'overridden',
        }
    f = DummyApp.describe_permission
    assert f('foo') == 'bar'
    assert f('post') == 'overridden'
    assert f('admin') == 'Set permissions.'
    assert f('does_not_exist') == ''


@pytest.fixture
def installed_app(request):
    """Returns an installed application instance."""
    project = create_project('myproject')
    app_config = create_app_config(project, 'my_mounted_app')
    app = Application(project, app_config)
    app.install(project)
    return app


class TestInstall(WithDatabase):
    patches = [fake_app_patch]

    def test_that_it_creates_a_discussion(self):
        def discussion_count():
            return model.Discussion.query.find().count()

        original_discussion_count = discussion_count()
        install_app()
        assert discussion_count() == original_discussion_count + 1


class TestDefaultDiscussion(WithDatabase):
    patches = [fake_app_patch]

    @pytest.fixture(autouse=True)
    def setup_discussion(self):
        install_app()
        self.discussion = model.Discussion.query.get(
            shortname='my_mounted_app')

    def test_that_it_has_a_description(self):
        assert self.discussion.description == 'Forum for my_mounted_app comments'

    def test_that_it_has_a_name(self):
        assert self.discussion.name == 'my_mounted_app Discussion'

    def test_that_its_shortname_is_taken_from_the_project(self):
        assert self.discussion.shortname == 'my_mounted_app'


class TestAppDefaults(WithDatabase):
    patches = [fake_app_patch]

    @pytest.fixture(autouse=True)
    def setup_app(self):
        self.app = install_app()

    def test_that_it_has_an_empty_sidebar_menu(self):
        assert self.app.sidebar_menu() == []

    def test_that_it_denies_access_for_everything(self):
        assert not self.app.has_access(model.User.anonymous(), 'any.topic')

    def test_default_sitemap(self):
        assert self.app.sitemap[0].label == 'My Mounted App'
        assert self.app.sitemap[0].url == '.'

    def test_not_exportable_by_default(self):
        assert not self.app.exportable

    def test_email_address(self):
        self.app.url = '/p/project/mount-point/'
        assert self.app.email_address == 'mount-point@project.p.in.localhost'


def install_app():
    """Helper function to create and install an application instance."""
    project = create_project('myproject')
    app_config = create_app_config(project, 'my_mounted_app')
    # XXX: Remove project argument to install; it's redundant
    app = Application(project, app_config)
    app.install(project)
    return app