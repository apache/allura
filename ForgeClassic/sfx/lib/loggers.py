from logging.handlers import WatchedFileHandler

class RTStatsHandler(WatchedFileHandler):
    fields=('action', 'action_type', 'tool_type', 'tool_mount', 'project', 'neighborhood',
            'username', 'url', 'ip_address')

    def __init__(self,
                 strftime_pattern,
                 module='allura',
                 page=1,
                 **kwargs):
        self.page = page
        self.module = module
        WatchedFileHandler.__init__(self, strftime_pattern)

    def emit(self, record):
        if not hasattr(record, 'action'):
            return
        kwpairs = dict(
            module=self.module,
            page=self.page)
        for name in self.fields:
            kwpairs[name] = getattr(record, name, None)
        kwpairs.update(getattr(record, 'kwpairs', {}))
        record.kwpairs = ','.join(
            '%s=%s' % (k,v) for k,v in sorted(kwpairs.iteritems())
            if v is not None)
        record.exc_info = None # Never put tracebacks in the rtstats log
        WatchedFileHandler.emit(self, record)
