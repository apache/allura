from sf.gobble.lib import fossforus_updater
from sf.gobble.queueworkers import QueueWorker


class F4UFeaturesWorker(QueueWorker):
    routing_keys=['f4u.*.features']

    def handle(self, shortname, source, **kwargs):
        return fossforus_updater.update_f4u_feature_list(
            shortname, source, self.host, **kwargs)

class F4UScreenshotsWorker(QueueWorker):
    routing_keys=['f4u.*.screenshots']

    def handle(self, shortname, source, **kwargs):
        return fossforus_updater.update_f4u_screenshots(
            shortname, source, self.host, **kwargs)

class F4UTagsWorker(QueueWorker):
    routing_keys=['f4u.*.tags']

    def handle(self, shortname, source, **kwargs):
        return fossforus_updater.update_f4u_tags(
            shortname, source, self.host, **kwargs)

class F4URatingsWorker(QueueWorker):
    routing_keys=['f4u.*.ratings']

    def handle(self, shortname, source, **kwargs):
        return fossforus_updater.update_f4u_ratings(
            shortname, source, self.host, **kwargs)
