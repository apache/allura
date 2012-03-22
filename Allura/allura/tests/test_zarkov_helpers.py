# -*- coding: utf-8 -*-
import unittest
from calendar import timegm
from datetime import datetime

import bson
import mock

from allura.lib import zarkov_helpers as zh

class TestZarkovClient(unittest.TestCase):

    def setUp(self):
        addr = 'tcp://0.0.0.0:0'
        ctx = mock.Mock()
        self.socket = mock.Mock()
        ctx.socket = mock.Mock(return_value=self.socket)
        PUSH=mock.Mock()
        with mock.patch('allura.lib.zarkov_helpers.zmq') as zmq:
            zmq.PUSH=PUSH
            zmq.Context.instance.return_value = ctx
            self.client = zh.ZarkovClient(addr)
        zmq.Context.instance.assert_called_once_with()
        ctx.socket.assert_called_once_with(PUSH)
        self.socket.connect.assert_called_once_with(addr)

    def test_event(self):
        self.client.event('test', dict(user='testuser'))
        obj = bson.BSON.encode(dict(
                type='test',
                context=dict(user='testuser'),
                extra=None))
        self.socket.send.assert_called_once_with(obj)

class TestZeroFill(unittest.TestCase):

    def setUp(self):
        self.dt_begin = datetime(2010, 6, 1)
        self.dt_end = datetime(2011, 7, 1)
        ts_begin = timegm(self.dt_begin.timetuple())
        ts_end = timegm(self.dt_end.timetuple())
        self.ts_ms_begin = ts_begin * 1000.0
        self.ts_ms_end = ts_end * 1000.0
        self.zarkov_data = dict(
            a=dict(
                a1=[ (self.ts_ms_begin, 1000), (self.ts_ms_end, 1000) ],
                a2=[ (self.ts_ms_begin, 1000), (self.ts_ms_end, 1000) ] ),
            b=dict(
                b1=[ (self.ts_ms_begin, 2000), (self.ts_ms_end, 2000) ],
                b2=[ (self.ts_ms_begin, 2000), (self.ts_ms_end, 2000) ] ))

    def test_to_utc_timestamp(self):
        self.assertEqual(
            zh.to_utc_timestamp(self.dt_begin),
            self.ts_ms_begin)
        self.assertEqual(
            zh.to_utc_timestamp(self.dt_end),
            self.ts_ms_end)

    def test_zero_fill_time_series_month(self):
        result = zh.zero_fill_time_series(
            self.zarkov_data['a']['a1'], 'month',
            datetime(2010, 5, 1), datetime(2011, 9, 1))
        self.assertEqual(result[0][1], 0)
        self.assertEqual(result[-1][1], 0)
        self.assertEqual(len(result), 17)
        self.assertEqual(result[1][1], 1000)
        self.assertEqual(result[-3][1], 1000)
        days_ms = 24 * 3600 * 1000
        min_delta = 28 * days_ms
        max_delta= 31 * days_ms
        for p1, p2 in zip(result, result[1:]):
            delta = p2[0]-p1[0]
            assert min_delta <= delta <= max_delta, delta

    def test_zero_fill_time_series_date(self):
        result = zh.zero_fill_time_series(
            self.zarkov_data['a']['a1'], 'date',
            datetime(2010, 5, 1), datetime(2011, 9, 1))
        self.assertEqual(len(result), 489)
        days_ms = 24 * 3600 * 1000
        for p1, p2 in zip(result, result[1:]):
            delta = p2[0]-p1[0]
            assert delta == days_ms

    def test_zero_fill_zarkov_month_dt(self):
        result = zh.zero_fill_zarkov_result(
            self.zarkov_data, 'month',
            datetime(2010, 5, 1), datetime(2011, 9, 1))
        a_result = result['a']['a1']
        b_result = result['b']['b2']
        self.assertEqual(a_result[0][1], 0)
        self.assertEqual(a_result[-1][1], 0)
        self.assertEqual(len(a_result), 17)
        self.assertEqual(a_result[1][1], 1000)
        self.assertEqual(a_result[-3][1], 1000)
        self.assertEqual(b_result[0][1], 0)
        self.assertEqual(b_result[-1][1], 0)
        self.assertEqual(len(b_result), 17)
        self.assertEqual(b_result[1][1], 2000)
        self.assertEqual(b_result[-3][1], 2000)

    def test_zero_fill_zarkov_month_str(self):
        result0 = zh.zero_fill_zarkov_result(
            self.zarkov_data, 'month',
            datetime(2010, 5, 1), datetime(2011, 9, 1))
        result1 = zh.zero_fill_zarkov_result(
            self.zarkov_data, 'month',
            '2010-5-1', '2011-09-1')
        self.assertEqual(result0, result1)
