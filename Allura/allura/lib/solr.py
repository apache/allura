import shlex
import pysolr


class Solr(pysolr.Solr):
    """Solr server that accepts default values for `commit` and
    `commitWithin` and passes those values through to each `add` and
    `delete` call, unless explicitly overridden.
    """

    def __init__(self, server, commit=True, commitWithin=None, **kw):
        pysolr.Solr.__init__(self, server, **kw)
        self.commit = commit
        self.commitWithin = commitWithin

    def add(self, *args, **kw):
        if 'commit' not in kw:
            kw['commit'] = self.commit
        if self.commitWithin and 'commitWithin' not in kw:
            kw['commitWithin'] = self.commitWithin
        return pysolr.Solr.add(self, *args, **kw)

    def delete(self, *args, **kw):
        if 'commit' not in kw:
            kw['commit'] = self.commit
        return pysolr.Solr.delete(self, *args, **kw)


class MockSOLR(object):

    class MockHits(list):
        @property
        def hits(self):
            return len(self)

        @property
        def docs(self):
            return self

    def __init__(self):
        self.db = {}

    def add(self, objects):
        for o in objects:
            o['text'] = ''.join(o['text'])
            self.db[o['id']] = o

    def commit(self):
        pass

    def search(self, q, fq=None, **kw):
        if isinstance(q, unicode):
            q = q.encode('latin-1')
        # Parse query
        preds = []
        q_parts = shlex.split(q)
        if fq: q_parts += fq
        for part in q_parts:
            if part == '&&':
                continue
            if ':' in part:
                field, value = part.split(':', 1)
                preds.append((field, value))
            else:
                preds.append(('text', part))
        result = self.MockHits()
        for obj in self.db.values():
            for field, value in preds:
                neg = False
                if field[0] == '!':
                    neg = True
                    field = field[1:]
                if field == 'text' or field.endswith('_t'):
                    if (value not in str(obj.get(field, ''))) ^ neg:
                        break
                else:
                    if (value != str(obj.get(field, ''))) ^ neg:
                        break
            else:
                result.append(obj)
        return result

    def delete(self, *args, **kwargs):
        if kwargs.get('q', None) == '*:*':
            self.db = {}
        elif kwargs.get('id', None):
            del self.db[kwargs['id']]
        elif kwargs.get('q', None):
            for doc in self.search(kwargs['q']):
                self.delete(id=doc['id'])

