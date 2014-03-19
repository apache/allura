"""
An Apache authorization handler for Allura

* This needs python-requests in the modpython path
* Check fuse/accessfs.py for more details on the path mangling
  magic

Here is a quick example for your apache settings (assuming ProxyPass)

    SetEnv GIT_PROJECT_ROOT /opt/allura/scm/git
    SetEnv GIT_HTTP_EXPORT_ALL
    ProxyPass /git/ !
    ScriptAlias /git/ /usr/lib/git-core/git-http-backend/

    <Location "/git/">
            AddHandler mod_python .py
            PythonAccessHandler /path/to/ApacheAccessHandler.py
            PythonDebug On

            AuthType Basic
            AuthName "Git Access"
            AuthBasicAuthoritative off
            PythonOption ALLURA_PERM_URL https://127.0.0.1/auth/repo_permissions
            PythonOption ALLURA_AUTH_URL https://127.0.0.1/auth/do_login
            PythonOption ALLURA_VIRTUALENV /var/local/env-allura
    </Location>

"""


from mod_python import apache
import os
import json


requests = None  # will be imported on demand, to allow for virtualenv


def log(req, message):
    req.log_error("Allura Access: %s" % message, apache.APLOG_WARNING)


def load_requests_lib(req):
    virtualenv_path = req.get_options().get('ALLURA_VIRTUALENV', None)
    if virtualenv_path:
        activate_this = '%s/bin/activate_this.py' % virtualenv_path
        execfile(activate_this, {'__file__': activate_this})
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
    parts = ['/SCM/%s.%s' % (proj, nbhd)] + rest
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


def check_authentication(req):
    auth_url = req.get_options().get('ALLURA_AUTH_URL', 'https://127.0.0.1/auth/do_login')
    r = requests.post(auth_url, allow_redirects=False, data={
        'username': req.user,
        'password': req.get_basic_auth_pw(),
        'return_to': '/login_successful'})
    return r.status_code == 302 and r.headers['location'].endswith('/login_successful')


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
        log(req, "error decoding JSON %s %s" % (r.headers['content-type'], ex))
        return False

    permission = get_permission_name(req_path, req_query, req.method)
    authorized = cred.get(permission, False)

    log(req, "%s -> %s -> %s -> authorized:%s" % (r.url, cred, permission, authorized))
    return authorized


def handler(req):
    load_requests_lib(req)
    req.add_common_vars()

    if not check_repo_path(req):
        return apache.HTTP_NOT_FOUND

    authenticated = check_authentication(req)
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
