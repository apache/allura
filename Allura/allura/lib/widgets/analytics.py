import ew

class GoogleAnalytics(ew.Widget):
    template='jinja:analytics.html'
    params=['account']
    account='UA-XXXXX-X'
    
