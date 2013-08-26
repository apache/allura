from ..base import ToolImporter
from forgetracker.tracker_main import ForgeTrackerApp

class GitHubTrackerImporter(ToolImporter):
    source = 'GitHub'
    target_app = ForgeTrackerApp
    controller = None
    tool_label = 'Issues'