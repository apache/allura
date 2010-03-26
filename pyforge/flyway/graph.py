import heapq
from itertools import product
from collections import defaultdict, namedtuple

def shortest_path(nodes, start, end):
    '''Dijkstra's algorithm for shortest path from the start Node to the end Node'''
    start.distance = 0
    unvisited = list(nodes)
    heapq.heapify(unvisited)
    while unvisited:
        cur = heapq.heappop(unvisited)
        if cur.distance is None:
            raise ValueError, 'No migration path exists from %s to %s' % (
                start, end)
        if cur in end:
            return list(cur.path())
        cur.visit()
        heapq.heapify(unvisited)


def gen_migration_states(migrations):
    '''Return all states referenced by the given migrations'''
    versions = defaultdict(lambda: [-1])
    for mod,version in migrations:
        versions[mod].append(version)
    State = namedtuple('State', versions)
    modules = versions.keys()
    states = [ State(*ver) for ver in product(*versions.values()) ]
    return State, modules, states

def index_migration_states(modules, states):
    '''Return an index from (module,version) => all states with that mod,version'''
    index = defaultdict(list)
    for s in states:
        for m in modules:
            v = getattr(s, m)
            index[m,v].append(s)
    return index

def build_graph(states, state_index, migrations):
    node_from_state = dict((s, Node(s)) for s in states)
    nodes = node_from_state.values()
    for m in migrations.itervalues():
        for direction in 'up', 'down':
            ms = MigrateStep(m, direction)
            for cur_state, next_state in ms.transitions(state_index):
                n = Node(ms)
                nodes.append(n)
                prev = node_from_state[cur_state]
                next = node_from_state[next_state]
                prev.succs.append(n)
                n.succs.append(next)
    return nodes

class MigrateStep(object):

    def __init__(self, migration, direction):
        self.migration = migration
        self.direction = direction

    def transitions(self, state_index):
        if self.direction == 'up':
            reqs = self.migration.up_requires()
            postcondition = self.migration.up_postcondition()
        else:
            reqs = self.migration.down_requires()
            postcondition = self.migration.down_postcondition()
        for prev in states_with(reqs, state_index):
            next = prev._replace(**postcondition)
            yield prev, next

    def apply(self, state):
        if self.direction == 'up':
            self.migration.up()
            state.update(self.migration.up_postcondition())
        else:
            self.migration.down()
            state.update(self.migration.down_postcondition())

    def __repr__(self):
        return '<%s.%s %s>' % (
            self.migration.module,
            self.migration.version,
            self.direction)

class Node(object):

    def __init__(self, data):
        self.data = data
        self.visited = False
        self.distance = None
        self.pred = None
        self.succs = []

    def visit(self):
        self.visited = True
        for succ in self.succs:
            if succ.visited: continue
            if self < succ:
                succ.distance = self.distance + 1
                succ.pred = self

    def path(self):
        if self.pred:
            for p in self.pred.path():
                yield p
        yield self.data

    def __lt__(self, other):
        if self.distance is None:
            return False
        if other.distance is None:
            return True
        return self.distance < other.distance

    def __repr__(self):
        return '<Node %r (%s)>' % (self.data,self.distance)

def states_with(requirements, state_index):
    states = None
    for (mod, ver) in requirements:
        if states is None: states = set(state_index[mod,ver])
        else: states &= set(state_index[mod,ver])
    return states



