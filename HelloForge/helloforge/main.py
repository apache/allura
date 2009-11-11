from tg import expose
from pyforge.app import Application

class HelloForgeApp(Application):
    '''This is the HelloWorld application for PyForge, showing
    all the rich, creamy goodness that is installable apps.
    '''
    default_config = dict(message='Custom message goes here')

    def __init__(self, config):
        self.config = config
        self.root = RootController(config['message'])


class RootController(object):

    def __init__(self, message):
        self.message = message

    @expose('helloforge.templates.index')
    def index(self):
        return dict(message=self.message)
                  

    
