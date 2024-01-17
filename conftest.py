import pytest

# should get rid of this once this issue is fixed https://github.com/TurboGears/tg2/issues/136
@pytest.fixture(autouse=True, scope='session')
def tg_context_patch():
    from tg import (
        request as r,
        tmpl_context as c,
        app_globals as g,
        cache,
        response,
        translator,
        url,
        config,
    )
    r.__dict__['_is_coroutine'] = False
    c.__dict__['_is_coroutine'] = False
    g.__dict__['_is_coroutine'] = False
    cache.__dict__['_is_coroutine'] = False
    response.__dict__['_is_coroutine'] = False
    translator.__dict__['_is_coroutine'] = False
    url.__dict__['_is_coroutine'] = False
    config.__dict__['_is_coroutine'] = False
                      