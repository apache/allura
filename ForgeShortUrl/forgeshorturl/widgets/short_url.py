from allura.lib.widgets import form_fields as ffw


class CreateShortUrlWidget(ffw.Lightbox):

    def resources(self):
        for r in super(CreateShortUrlWidget, self).resources():
            yield r
