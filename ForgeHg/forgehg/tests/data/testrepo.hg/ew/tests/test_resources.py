import pkg_resources
from config import TestConfig, app_from_config
from formencode.variabledecode import variable_encode

from ew import resource

def setup_noDB():
    base_config = TestConfig(folder = None,
                             values = {'use_sqlalchemy': False,
                                       'ignore_parameters': ["ignore", "ignore_me"],
                                       'use_dotted_templatenames':'true',
                             }
                             )
    app = app_from_config(base_config)
    resource.ResourceManager.register_all_resources()
    return app

app = setup_noDB()

def test_simple():
    response = app.get('/res/')
    for x in response.html('script'):
        if x.has_key('src') and not x['src'].startswith('http'):
            res = app.get(x['src'])
    for x in response.html('head')[0]('link') :
        if x.has_key('href') and not x['href'].startswith('http'):
            res = app.get(x['href'])

def test_badpath():
    resource.ResourceManager.register_directory(
        'foo', pkg_resources.resource_filename('ew', 'tests'))
    # Fetch the file (successfully)
    app.get('/_ew_resources/foo/test_resources.py')
    # Try to break out of the resource subdir
    app.get('/_ew_resources/foo/../foo/test_resources.py', status=404)

def test_register():
    resource.ResourceManager.register_directory(
        'test', pkg_resources.resource_filename('ew.tests', 'static'))
    resource.ResourceManager.register_directory(
        'test', pkg_resources.resource_filename('ew.tests', 'static'))
