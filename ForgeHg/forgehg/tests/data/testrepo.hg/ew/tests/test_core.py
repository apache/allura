from datetime import date, time

from nose.tools import raises, assert_raises

from config import TestConfig, app_from_config
from formencode.variabledecode import variable_encode
from formencode import validators as fev

import ew

def setup_noDB():
    base_config = TestConfig(folder = None,
                             values = {'use_sqlalchemy': False,
                                       'ignore_parameters': ["ignore", "ignore_me"],
                                       'use_dotted_templatenames':'true',
                             }
                             )
    return app_from_config(base_config)

app = setup_noDB()

def test_simple():
    response = app.get('/', params=dict(a=5, b=6))
    assert "<pre>{'value':" in response, response

@raises(AssertionError)
def test_bad_template():
    response = app.get('/index_bad_template')

def test_input():
    response = app.get('/index_input')
    assert '<input' in response

def test_simple_validate():
    response = app.post('/validate_input', params=dict(foo='foobar'))
    assert response.body == 'foobar'
    response = app.post('/validate_input', params=dict(foo='foo'))
    assert 'error' in response
    assert 'value="foo"' in response, response

def test_nested_form():
    json = dict(foo=dict(a='foobar', b='foobar'))
    response = app.post('/validate_nested',
                        params=variable_encode(json, add_repetitions=False))
    assert response.json == json, response.json
    json = dict(foo=dict(a='foo', b='foobar'))
    response = app.post('/validate_nested',
                        params=variable_encode(json, add_repetitions=False))
    assert 'error' in response
    json = dict(foo=dict(a='foobar', b='foo'))
    response = app.post('/validate_nested',
                        params=variable_encode(json, add_repetitions=False))
    assert 'error' in response

def test_repeated_field():
    response = app.get('/index_repeated')
    json = dict(a=['one', 'two', 'three'])
    response = app.post('/validate_repeated',
                        params=variable_encode(json, add_repetitions=False))
    assert 'error' in response

def test_fieldsets():
    response = app.get('/index_nested_fs')
    assert 'name="foo.a"' in response
    assert 'name="foo.b"' in response
    assert 'name="c"' in response
    assert 'name="d"' in response
    json = dict(foo=dict(a='one', b='two'),
                c='three',
                d='four')
    response = app.post('/validate_nested_fs',
                        params=variable_encode(json, add_repetitions=False))
    assert 'error' in response
    assert 'name="foo.a"' in response
    assert 'name="foo.b"' in response
    assert 'name="c"' in response
    assert 'name="d"' in response
    assert 'value="one"' in response
    assert 'value="two"' in response
    assert 'value="three"' in response
    assert 'value="four"' in response
    json = dict(foo=dict(a='one__', b='two__'),
                c='three',
                d='four__')
    response = app.post('/validate_nested_fs',
                        params=variable_encode(json, add_repetitions=False))
    assert response.json == json, response.json

def test_table():
    response = app.get('/index_table')
    assert 'foo-0.a' in response
    assert 'foo-4.b' in response
    json = dict(foo=[ dict(a=i, b=i) for i in xrange(5) ])
    response = app.post('/validate_table',
                        params=variable_encode(json, add_repetitions=False))
    for i in xrange(5):
        assert 'value="%d"' % i in response, response

def test_controller_widget():
    response = app.get('/index_cw', params=dict(a=5, b=7))
    assert response.json == dict(a='5', b='7'), response.json
    json = dict(a=5, b=7)
    response = app.post('/validate_cw', params=json)
    assert json == response.json
    json = dict(a='foo', b=7)
    response = app.post('/validate_cw', params=json)
    assert response.json['errors']['a'] == 'Please enter a number', response.json

def test_select():
    r = app.get('/index_select_form')
    r = app.get('/index_select_form', params=dict(a=3, b=5))
    assert 'fielderror' in r, r
    r = app.get('/index_select_form', params={
            'a':3,
            'b-0':1,
            'b-1':2})

def test_validators():
    curr = ew.Currency()
    vtime = ew.TimeConverter()
    vdate = ew.DateConverter()
    oo0 = ew.OneOf(range(3))
    oo1 = ew.OneOf(lambda:range(3))
    oo2 = ew.OneOf(lambda:range(3))
    oo2.hideList = True
    us0 = ew.UnicodeString(outputEncoding='utf-8')
    us1 = ew.UnicodeString(outputEncoding='utf-16')
    tests = [
        (curr, 5522, '$55.22'),
        (vtime, time(10,12,55), '10:12:55'),
        (vdate, date(1975,5,22), '05/22/1975'),
        (oo0, 2, 2),
        (oo1, 2, 2),
        (us0, u'foo', u'foo'),
        (us1, u'foo', u'foo'),
        ]
    for val, py, st in tests:
        assert val.from_python(py, None) == st
        assert val.to_python(st, None) == py
    assert curr.from_python('$55.22', None) == '$55.22'
    assert_raises(fev.Invalid, vdate.to_python, '5/5/foo', None)
    assert_raises(fev.Invalid, oo2.to_python, 5, None)

def test_big_form():
    r = app.get('/index_bigtest_form')

def test_double_form():
    r = app.get('/index_double_form')
    assert 'value="5"' in r
    assert 'value="15"' in r
    r = app.post('/validate_double_a', params={
            'a.x':'a5'})
    assert 'value="a5"' in r # a has bad input value
    assert 'value="15"' in r # b is unchanged

