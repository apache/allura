import ew

class GoogleAnalytics(ew.Widget):
    template='genshi:allura.lib.widgets.templates.analytics'
    params=['account']
    account='UA-XXXXX-X'
    
