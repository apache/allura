from datetime import datetime
from decimal import Decimal
from unittest import TestCase, main

import mock

from ming.base import Object, Document, Field, Cursor
from ming import schema as S
from pymongo.bson import ObjectId

class TestSchemaItem(TestCase):

    def test_make_array(self):
        si_any = S.SchemaItem.make([])
        si_int = S.SchemaItem.make([int])
        self.assertEqual(S.Array, si_any.__class__)
        self.assertEqual(S.Anything, si_any.field_type.__class__)
        self.assertEqual(S.Int, si_int.field_type.__class__)
        self.assertRaises(ValueError, S.SchemaItem.make, [int, str])

    def test_migrate(self):
        si = S.Migrate(int, str, str)
        self.assertEqual(si.validate(1), '1')
        self.assertEqual(si.validate('1'), '1')
        si = S.Migrate(
            {str:{'a':int}},
            [ dict(key=str, a=int) ],
            S.Migrate.obj_to_list('key'))
        self.assertEqual(si.validate(dict(foo=dict(a=1))),
                         [ dict(key='foo', a=1) ])
        si = S.Migrate(
            {str:int},
            [ dict(key=str, value=int) ],
            S.Migrate.obj_to_list('key', 'value'))
        self.assertEqual(si.validate(dict(foo=1)),
                         [ dict(key='foo', value=1) ])

    def test_deprecated(self):
        si = S.SchemaItem.make(dict(
                a=S.Deprecated(),
                b=int))
        self.assertEqual(si.validate(dict(a=5, b=6)),
                         dict(b=6))

    def test_fancy(self):
        si = S.SchemaItem.make(dict(
                a=S.Int(required=True),
                b=S.Int(if_missing=5)))
        self.assertRaises(S.Invalid, si.validate, dict(b=10))
        self.assertEqual(si.validate(dict(a=10)),
                         dict(a=10, b=5))

    def test_validation(self):
        si = S.SchemaItem.make({str:int})
        self.assertEqual(si.validate(dict(a=5)), dict(a=5))
        self.assertRaises(S.Invalid, si.validate, dict(a='as'))
        self.assertRaises(S.Invalid, si.validate, {5:5})

if __name__ == '__main__':
    main()

