from paste.registry import StackedObjectProxy

c = StackedObjectProxy(name='c')
g = StackedObjectProxy(name='g')
request = StackedObjectProxy(name='request')
response = StackedObjectProxy(name='response')
environ = StackedObjectProxy(name='environ')
config = StackedObjectProxy(name='config')
session = StackedObjectProxy(name='session')
