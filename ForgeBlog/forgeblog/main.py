
from tg.decorators import expose

from allura.app import Application
from allura.controllers import BaseController

#raise Exception(1)

class ForgeBlogApp(Application):
    __version__ = "1.2"
    tool_label='Blog'
    tool_description="""
        Share exciting news and progress updates with your
        community.
    """
    default_mount_label='Blog'
    default_mount_point='blog'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=14
    installable=True
    config_options = Application.config_options
    default_external_feeds = []
    icons={
        24:'images/blog_24.png',
        32:'images/blog_32.png',
        48:'images/blog_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        #self.admin = BlogAdminController(self)


class RootController(BaseController):


    @expose('jinja:forgeblog:templates/blog/index.html')
    #@with_trailing_slash
    def index(self, page=0, limit=10, **kw):
        return 'asf'