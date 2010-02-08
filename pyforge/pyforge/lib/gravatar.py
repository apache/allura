import re, urllib, hashlib

_wrapped_email=re.compile(r'.*<(.+)>')

def id(email):
    match = _wrapped_email.match(email)
    if match:
        email = match.group(1)
    return hashlib.md5(email.strip().lower()).hexdigest()

def url(email=None, gravatar_id=None, **kw):
    assert gravatar_id or email
    if gravatar_id is None:
        gravatar_id = id(email)
    if 'r' not in kw and 'rating' not in kw: kw['r'] = 'pg'
    if 'd' not in kw and 'default' not in kw: kw['d'] = 'wavatar'
    return ('http://gravatar.com/avatar/'
            + gravatar_id
            + '?' + urllib.urlencode(kw))

def for_user(user):
    return url(user.preferences['email_address'])
