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
            PythonOption ALLURA_PERM_URL http://127.0.0.1:8080/auth/repo_permissions
            PythonOption ALLURA_LDAP_BASE ou=people,dc=opensourceprojects,dc=eu
    </Location>

"""


from mod_python import apache
import os
# because urllib is not for humans
import requests
import json
import ldap


def log(req, message):
    req.log_error("Allura Access: %s" % message, apache.APLOG_WARNING)


def ldap_auth(req, username, password):
    """
    Return True if the user was authenticated via LDAP
    """

    l = ldap.initialize('ldap://127.0.0.1')
    l.protocol_version = ldap.VERSION3
    ldap_user = "uid=%s,%s" % (username, req.get_options().get('ALLURA_LDAP_BASE', 'ou=people,dc=example,dc=com'))

    try:
        l.simple_bind_s(ldap_user, password)
    except ldap.LDAPError as e:
        log(req, "Unable to authenticate user, %s %s" % (ldap_user, e))
        return False
    log(req, "LDAP user authenticated %s" % ldap_user)

    return True


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
    log(req, "USER: "+req.user)
    return ldap_auth(req, req.user, req.get_basic_auth_pw())


def check_permissions(req):
    req_path = str(req.parsed_uri[apache.URI_PATH])
    req_query = str(req.parsed_uri[apache.URI_QUERY])
    perm_url = req.get_options().get('ALLURA_PERM_URL', 'http://127.0.0.1:8080/auth/repo_permissions')
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
    req.add_common_vars()

    if not check_repo_path(req):
        return apache.HTTP_NOT_FOUND

    if req.user and not check_authentication(req):
        return apache.HTTP_UNAUTHORIZED

    if not check_permissions(req):
        return apache.HTTP_FORBIDDEN

    return apache.OK


def accesshandler(req):
    log(req, "AccessHandler")
    return handler(req)
