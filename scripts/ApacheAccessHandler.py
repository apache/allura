#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

"""
An Apache authorization handler for Allura

* This needs python-requests in the modpython path
* Check fuse/accessfs.py for more details on the path mangling
  magic

See scm_host.rst for documentation on how to configure Apache with this handler file.

This could also use the Allura code and authorize directly, but it's useful to be able to run
this authorization code without Allura set up and configured on the git host.
"""


from mod_python import apache
import os
import json
import re


requests = None  # will be imported on demand, to allow for virtualenv


def log(req, message):
    req.log_error("Allura Access: %s" % message, apache.APLOG_WARNING)


def load_requests_lib(req):
    virtualenv_path = req.get_options().get('ALLURA_VIRTUALENV', None)
    if virtualenv_path:
        activate_this = '%s/bin/activate_this.py' % virtualenv_path
        try:
            exec(compile(open(activate_this, "rb").read(), activate_this, 'exec'), {'__file__': activate_this})
        except Exception as e:
            log(req, f"Couldn't activate venv via {activate_this}: {repr(e)}")
    global requests
    import requests as requests_lib
    requests = requests_lib


# This came straight from accessfs.py
def mangle(path):
    '''Convert paths from the form /SCM/neighborhood/project/a/b/c to
    /SCM/project.neighborhood/a/b/c
    '''
    parts = [p for p in path.split(os.path.sep) if p]
    if len(parts) < 4:
        return None
    scm, nbhd, proj, rest = parts[0], parts[1], parts[2], parts[3:]
    parts = [f'/SCM/{proj}.{nbhd}'] + rest
    return '/'.join(parts)


def get_permission_name(req_path, req_query, req_method):
    """
    Determine whether the request is trying to read or write,
    and return the name of the appropriate permission to check.
    """
    if req_path.startswith('/git/'):
        if req_path.endswith('/git-receive-pack') or 'service=git-receive-pack' in req_query:
            return 'allow_write'
        else:
            return 'allow_read'
    elif req_path.startswith('/svn/'):
        if req_method in ('MKACTIVITY', 'PROPPATCH', 'PUT', 'CHECKOUT', 'MKCOL',
                          'MOVE', 'COPY', 'DELETE', 'LOCK', 'UNLOCK', 'MERGE', 'POST'):
            return 'allow_write'
        elif req_method in ("GET", "PROPFIND", "OPTIONS", "REPORT"):
            return 'allow_read'
        else:
            return 'allow_write'  # default to requiring write permission
    elif req_path.startswith('/hg/'):
        return 'allow_write'  # TODO: Differentiate reads and write for Hg


def check_repo_path(req):
    repo_path = mangle(str(req.parsed_uri[apache.URI_PATH]))
    return repo_path is not None


class RateLimitExceeded(Exception):
    pass


def check_authentication(req):
    password = req.get_basic_auth_pw()  # MUST be called before req.user
    username = req.user
    log(req, "checking auth for: %s" % username)
    if not username or not password:
        return False
    auth_url = req.get_options().get('ALLURA_AUTH_URL', 'https://127.0.0.1/auth/do_login')

    # work through our own Antispam protection
    auth_form_url = auth_url.replace('/do_login', '/')
    auth_form_page = requests.get(auth_form_url, allow_redirects=False).text
    auth_inputs = re.findall(r'(<input.*?>)', auth_form_page, re.I)
    re_name = re.compile(r''' name=["']?(.*?)["' />]''')
    re_value = re.compile(r''' value=["']?(.*?)["' />]''')
    for i, input in enumerate(auth_inputs):
        if 'password' in input:
            password_field = re_name.search(input).group(1)
            username_field = re_name.search(auth_inputs[i-1]).group(1)
        if 'spinner' in input:
            spinner_value = re_value.search(input).group(1)
            honey1_field = re_name.search(auth_inputs[i+1]).group(1)
            honey2_field = re_name.search(auth_inputs[i+2]).group(1)
        if 'timestamp' in input:
            timestamp_value = re_value.search(input).group(1)

    r = requests.post(auth_url, allow_redirects=False, data={
        username_field: username,
        password_field: password,
        'timestamp': timestamp_value,
        'spinner': spinner_value,
        honey1_field: '',
        honey2_field: '',
        'return_to': '/login_successful',
        '_session_id': 'this-is-our-session',
    }, cookies={
        '_session_id': 'this-is-our-session',
    })
    if r.status_code == 302 and r.headers['location'].endswith('/login_successful'):
        return True
    else:
        # try 2FA
        password, code = password[:-6], password[-6:]
        log(req, 'trying multifactor for user: %s' % username)
        sess = requests.Session()
        r = sess.post(auth_url, allow_redirects=False, data={
            username_field: username,
            password_field: password,
            'timestamp': timestamp_value,
            'spinner': spinner_value,
            honey1_field: '',
            honey2_field: '',
            'return_to': '/login_successful',
            '_session_id': 'this-is-our-session',
        }, cookies={
            '_session_id': 'this-is-our-session',
        })
        if r.status_code == 302 and '/auth/multifactor' in r.headers['location']:
            multifactor_url = auth_url.replace('do_login', 'do_multifactor')
            r = sess.post(multifactor_url, allow_redirects=False, data={
                'mode': 'totp',
                'code': code,
                'return_to': '/login_successful',
                '_session_id': 'this-is-our-session',
            }, cookies={
                '_session_id': 'this-is-our-session',
            })
            if r.status_code == 302 and r.headers['location'].endswith('/login_successful'):
                return True
            else:
                if 'rate limit exceeded' in r.text:
                    raise RateLimitExceeded()
    return False


def check_permissions(req):
    req_path = str(req.parsed_uri[apache.URI_PATH])
    req_query = str(req.parsed_uri[apache.URI_QUERY])
    perm_url = req.get_options().get('ALLURA_PERM_URL', 'https://127.0.0.1/auth/repo_permissions')
    r = requests.get(perm_url, params={'username': req.user, 'repo_path': mangle(req_path)})
    if r.status_code != 200:
        log(req, "repo_permissions return error (%d)" % r.status_code)
        return False

    try:
        cred = json.loads(r.content)
    except Exception as ex:
        log(req, "error decoding JSON {} {}".format(r.headers['content-type'], ex))
        return False

    permission = get_permission_name(req_path, req_query, req.method)
    authorized = cred.get(permission, False)

    log(req, f"{r.url} -> {cred} -> {permission} -> authorized:{authorized}")
    return authorized


def handler(req):
    load_requests_lib(req)
    req.add_common_vars()

    if not check_repo_path(req):
        log(req, 'path not found in Allura for URL %s' % req.parsed_uri[apache.URI_PATH])
        return apache.HTTP_NOT_FOUND
    try:
        authenticated = check_authentication(req)
    except RateLimitExceeded as e:
        # HTTP "Too Many Requests" to give the user a bit of a hint about why it failed
        return 429
    if req.user and not authenticated:
        return apache.HTTP_UNAUTHORIZED

    authorized = check_permissions(req)
    if not req.user and not authorized:
        return apache.HTTP_UNAUTHORIZED
    elif not authorized:
        return apache.HTTP_FORBIDDEN

    return apache.OK


def accesshandler(req):
    log(req, "AccessHandler")
    return handler(req)
