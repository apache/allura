from allura import model as M
from ming.orm import ThreadLocalORMSession

for app in M.AppConfig.query.find(dict(tool_name="svn")).all():
    if 'checkout_url' not in app.options:
        app.options.checkout_url='trunk'
    ThreadLocalORMSession.flush_all()
