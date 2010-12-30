import ew

class GoogleAnalytics(ew.Widget):
    template='jinja:widgets/analytics.html'
    defaults=dict(
        ew.Widget.defaults,
        account='UA-XXXXX-X')
    
    
