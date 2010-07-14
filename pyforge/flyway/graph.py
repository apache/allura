from itertools import product
from collections import defaultdict, namedtuple

class MigrationGraph(object):

    def __init__(self, migrations):
        self._build_graph(migrations)

    def reset(self):
        for n in self._nodes: n.reset()

    def _build_graph(self, migrations):
        '''Build a graph where the nodes are possible migration states and the
        edges are transitions between states allowed by migrations.
        '''
        # Generate all states referenced by the given migrations.  Also index
        # nodes by state.
        versions = defaultdict(lambda: [-1])
        for mod,version in migrations:
            versions[mod].append(version)
        self._State = namedtuple('State', versions)
        self._modules = versions.keys()
        self._nodes = [ Node(self._State(*ver)) for ver in product(*versions.values()) ]
        self.node_by_state = dict((n.state, n) for n in self._nodes)

        # Index the nodes by (mod,version)
        self._index = defaultdict(list)
        for n in self._nodes:
            for m in self._modules:
                v = getattr(n.state, m)
                self._index[m,v].append(n)

        # Add edges for all the migrations
        for m in migrations.itervalues():
            for direction in 'up', 'down':
                ms = MigrateStep(self, m, direction)
                for prev, next in ms.transitions():
                    prev.succs.append((next, ms))

    def nodes_with(self, requirements):
        '''Return list of nodes that match the requirements listed in
        requirements, which is either a dict or list of (mod,version) pairs.'''
        if isinstance(requirements, dict):
            requirements = requirements.iteritems()
        nodes = None
        for (mod, ver) in requirements:
            if nodes is None: nodes = set(self._index[mod,ver])
            else: nodes &= set(self._index[mod,ver])
        return nodes

    def shortest_path(self, start_requirements, end_requirements):
        '''Dijkstra's algorithm for shortest path from the start Node to any end
        Node'''
        # Find the start node
        start = dict((m, -1) for m in self._modules)
        start.update(start_requirements)
        start = dict((str(k), v) for k,v in start.iteritems()
                     if k in self._State._fields)
        start_state = self._State(**start)
        start = self.node_by_state[start_state]
        # Find the end node(s)
        end = self.nodes_with(end_requirements)
        # Run the algorithm
        start.distance = 0
        nodes = priority_dict(
            (node, node.distance)
            for node in self._nodes)
        while nodes:
            cur = nodes.pop_smallest()
            if cur.distance is None: # pragma no cover
                raise ValueError, 'No migration path exists from %s to %s' % (
                    start, end)
            if cur in end:
                return list(cur.path())
            cur.visit(nodes)

    def as_dot(self): # pragma no cover
        yield 'digraph G {'
        for n in self._nodes:
            yield 'node_%d[label="%r"];' % (id(n), n.state)
        for n in self._nodes:
            for (next, ms) in n.succs:
                yield 'node_%d->node_%d[label="%r"];' % (id(n), id(next), ms)
        yield '}'

class MigrateStep(object):
    '''Object representing a single migration step in a single direction (either
    up or down'''

    def __init__(self, graph, migration, direction):
        self.graph = graph
        self.migration = migration
        self.direction = direction

    def transitions(self):
        '''Returns all node->node transitions made possible by this migratestep'''
        if self.direction == 'up':
            reqs = self.migration.up_requires()
            postcondition = self.migration.up_postcondition()
        else:
            reqs = self.migration.down_requires()
            postcondition = self.migration.down_postcondition()
        for prev in self.graph.nodes_with(reqs):
            next_state = prev.state._replace(**postcondition)
            next = self.graph.node_by_state[next_state]
            yield prev, next

    def apply(self, state):
        '''Actually run the migration, updating the state passed in'''
        if self.direction == 'up':
            self.migration.up()
            state.update(self.migration.up_postcondition())
        else:
            self.migration.down()
            state.update(self.migration.down_postcondition())

    def __repr__(self): # pragma no cover
        return '<%s.%s %s>' % (
            self.migration.module,
            self.migration.version,
            self.direction)

class Node(object):

    def __init__(self, state):
        self.state = state
        self.succs = [] # list of (state, migrationstep)
        self.reset()

    def reset(self):
        self.visited = False
        self.pred = None # (state, migrationstep)
        self.distance = 1e9 # effectively inf

    def visit(self, nodes):
        '''The 'visit' step of Dijkstra's shortest-path algorithm'''
        self.visited = True
        new_dist = self.distance + 1
        for succ, ms in self.succs:
            if succ.visited: continue
            if new_dist < succ.distance:
                succ.distance = new_dist
                succ.pred = (self, ms)
                nodes[succ] = new_dist

    def path(self):
        '''Read back the shortest path from the 'predecessor' field'''
        if self.pred:
            for p in self.pred[0].path():
                yield p
            yield self.pred[1]

    def __repr__(self): # pragma no cover
        return '<Node %r (%s)>' % (self.state,self.distance)

# priority dictionary recipe copied from 
# http://code.activestate.com/recipes/522995-priority-dict-a-priority-queue-with-updatable-prio/
# We use this rather than the raw heap because the priority_dict allows us to
# update the priority of a node, which heapq does not (natively) allow without
# re-running heapify() each time a priority changes.  (And priorities change
# often in Dijkstra's algorithm.)
from heapq import heapify, heappush, heappop

class priority_dict(dict):
    """Dictionary that can be used as a priority queue.

    Keys of the dictionary are items to be put into the queue, and values
    are their respective priorities. All dictionary methods work as expected.
    The advantage over a standard heapq-based priority queue is
    that priorities of items can be efficiently updated (amortized O(1))
    using code as 'thedict[item] = new_priority.'

    The 'smallest' method can be used to return the object with lowest
    priority, and 'pop_smallest' also removes it.

    The 'sorted_iter' method provides a destructive sorted iterator.
    """
    
    def __init__(self, *args, **kwargs):
        super(priority_dict, self).__init__(*args, **kwargs)
        self._rebuild_heap()

    def _rebuild_heap(self):
        self._heap = [(v, k) for k, v in self.iteritems()]
        heapify(self._heap)

    def smallest(self):
        """Return the item with the lowest priority.

        Raises IndexError if the object is empty.
        """
        
        heap = self._heap
        v, k = heap[0]
        while k not in self or self[k] != v:
            heappop(heap)
            v, k = heap[0]
        return k

    def pop_smallest(self):
        """Return the item with the lowest priority and remove it.

        Raises IndexError if the object is empty.
        """
        
        heap = self._heap
        v, k = heappop(heap)
        while k not in self or self[k] != v:
            v, k = heappop(heap)
        del self[k]
        return k

    def __setitem__(self, key, val):
        # We are not going to remove the previous value from the heap,
        # since this would have a cost O(n).
        
        super(priority_dict, self).__setitem__(key, val)
        
        if len(self._heap) < 2 * len(self):
            heappush(self._heap, (val, key))
        else:
            # When the heap grows larger than 2 * len(self), we rebuild it
            # from scratch to avoid wasting too much memory.
            self._rebuild_heap()

    def setdefault(self, key, val):
        if key not in self:
            self[key] = val
            return val
        return self[key]

    def update(self, *args, **kwargs):
        # Reimplementing dict.update is tricky -- see e.g.
        # http://mail.python.org/pipermail/python-ideas/2007-May/000744.html
        # We just rebuild the heap from scratch after passing to super.
        
        super(priority_dict, self).update(*args, **kwargs)
        self._rebuild_heap()

    def sorted_iter(self):
        """Sorted iterator of the priority dictionary items.

        Beware: this will destroy elements as they are returned.
        """
        
        while self:
            yield self.pop_smallest()
# End recipe
