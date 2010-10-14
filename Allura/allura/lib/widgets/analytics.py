import ew

class GoogleAnalytics(ew.Widget):
    template='jinja:widgets/analytics.html'
    params=['account']
    account='UA-XXXXX-X'
    
