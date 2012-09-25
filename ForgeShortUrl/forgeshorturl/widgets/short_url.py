from allura.lib.widgets import form_fields as ffw


class CreateShortUrlWidget(ffw.Lightbox):

    def resources(self):
        for r in super(CreateShortUrlWidget, self).resources():
            yield r


class UpdateShortUrlWidget(ffw.Lightbox):
    defaults = dict(
            ffw.Lightbox.defaults,
            name='update-short-url-modal',
            trigger='a.update-url')
