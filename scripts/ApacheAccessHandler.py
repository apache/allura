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
import re
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
    scm, nbhd, proj, rest = parts[0], parts[1], parts[2], parts[3:]
    parts = ['/SCM/%s.%s' % (proj, nbhd)] + rest
    return '/'.join(parts)


def handler(req):
    req.add_common_vars()
    req_path = str(req.parsed_uri[apache.URI_PATH])
    req_query = str(req.parsed_uri[apache.URI_QUERY])

    req_passwd = req.get_basic_auth_pw()
    req_user = req.user
    req_method = req.method

    log(req, "PATH: %s QUERY: %s METHOD: %s" % (req_path, req_query, req_method))

    try:
        params = {'repo_path': mangle(req_path)}
    except:
        return apache.HTTP_NOT_FOUND

    if req_user:
        log(req, "USER: "+req_user)
        params['username'] = req_user
        if not ldap_auth(req, req.user, req_passwd):
            return apache.HTTP_UNAUTHORIZED
            #return apache.HTTP_FORBIDDEN
        log(req, "USER: "+req.user)
    else:
        log(req, "USER: Anonymous")

    url = req.get_options().get('ALLURA_PERM_URL', 'http://127.0.0.1:8080/auth/repo_permissions')
    r = requests.get(url, params=params)
    if r.status_code != 200:
        log(req, "repo_permissions return error (%d)" % r.status_code)
        return apache.HTTP_FORBIDDEN

    try:
        cred = json.loads(r.content)
    except Exception as ex:
        log(req, "error decoding JSON %s %s" % (r.headers['content-type'], ex))
        return apache.HTTP_FORBIDDEN

    #
    # Distinguish READ and WRITE
    #
    # TODO: HG
    #

    authorized = False
    # GIT
    if re.match('^/git/.*', req_path):
        if re.match('.*/git-receive-pack', req_path) or re.match('service=git-receive-pack', req_query):
            # Write access
            log(req, "Request is GIT Auth Write")
            authorized = cred.get('allow_write', False)
        else:
            # Read access
            log(req, "Request is GIT Auth READ")
            authorized = cred.get('allow_read', False)
    # SVN
    if re.match('^/svn/.*', req_path):
        if req_method in ('MKACTIVITY', 'PROPPATCH', 'PUT', 'CHECKOUT', 'MKCOL',
                          'MOVE', 'COPY', 'DELETE', 'LOCK', 'UNLOCK', 'MERGE', 'POST'):
            # Write access
            log(req, "Request is SVN Auth WRITE")
            authorized = cred.get('allow_write', False)
        elif req_method in ("GET", "PROPFIND", "OPTIONS", "REPORT"):
            # Read access
            log(req, "Request is SVN Auth READ")
            authorized = cred.get('allow_read', False)
        else:
            log(req, "Request is SVN unknown %s" % req_method)

    log(req, "%s -> %s -> authorized:%s" % (r.url, cred, authorized))

    if authorized:
        log(req, "Request ACCEPTED")
        return apache.OK
    elif req.user:
        log(req, "Request FORBIDDEN")
        return apache.HTTP_UNAUTHORIZED
        #return apache.HTTP_FORBIDDEN
    else:
        log(req, "Request UNAUTHORIZED")
        return apache.HTTP_UNAUTHORIZED


def accesshandler(req):
    log(req, "AccessHandler")
    return handler(req)
