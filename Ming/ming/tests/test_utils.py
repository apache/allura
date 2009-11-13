from unittest import TestCase, main

from ming import utils

class TestUtils(TestCase):

    def test_lazy_property(self):
        counter = [ 0 ]
        class MyClass(object):
            @utils.LazyProperty
            def prop(self):
                counter[0] += 1
                return 5
        obj = MyClass()
        self.assertEqual(counter, [0])
        self.assertEqual(obj.prop, 5)
        self.assertEqual(counter, [1])
        self.assertEqual(obj.prop, 5)
        self.assertEqual(counter, [1])

    def test_uri_parse(self):
        uri = 'mongo://user:password@host:100/path?a=5'
        result = utils.parse_uri(uri, b='5')
        self.assertEqual(result, dict(
                scheme='mongo',
                host='host',
                username='user',
                password='password',
                port=100,
                path='/path',
                query=dict(a='5', b='5')))
        

if __name__ == '__main__':
    main()

