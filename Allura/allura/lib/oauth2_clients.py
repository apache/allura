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

"""OAuth2 clients registered by a machine rather than a user: redirect URI rules, and Client ID Metadata Documents
(draft-ietf-oauth-client-id-metadata-document), where an https client_id hosts its own metadata"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import urllib3
from pymongo import ReturnDocument
from tg import config

from allura import model as M
from allura.lib import helpers as h

log = logging.getLogger(__name__)

MAX_REDIRECT_URIS = 10
MAX_NAME_LEN = 200

# RFC 8252 native clients redirect to a loopback address on a port they pick per session
LOOPBACK_HOSTS = ('127.0.0.1', '::1', 'localhost')


def _loopback_key(uri: str) -> tuple | None:
    """An http loopback URI with its port dropped, for comparison; None for anything else"""
    try:
        p = urlsplit(uri)
        host = p.hostname
    except ValueError:
        return None
    # .hostname drops userinfo, so `http://evil@localhost/` must be refused explicitly
    if p.scheme != 'http' or host not in LOOPBACK_HOSTS or '@' in p.netloc:
        return None
    return host, p.path, p.query, p.fragment


def https_or_loopback(uri: str) -> bool:
    return uri.startswith('https://') or _loopback_key(uri) is not None


def redirect_uri_matches(uri: str, registered: list[str]) -> bool:
    """Exact match, except that a loopback redirect may use any port (RFC 8252 section 7.3)"""
    if uri in registered:
        return True
    key = _loopback_key(uri)
    return key is not None and key in {_loopback_key(r) for r in registered}


# The metadata fetch goes to a URL anyone can choose, so it only goes to public addresses, pinned to the address
# that was checked, with no redirects and a small size cap.  None of this is configurable.
CIMD_MAX_BYTES = 5 * 1024
CIMD_TIMEOUT = urllib3.Timeout(connect=5, read=5)
CIMD_MIN_TTL = 5 * 60
CIMD_MAX_TTL = 24 * 60 * 60
CIMD_DEFAULT_TTL = 60 * 60


class CIMDError(Exception):
    pass


def is_cimd_client_id(client_id) -> bool:
    # other client ids are nonces, so a URL can only be a metadata document
    return isinstance(client_id, str) and client_id.startswith('https://')


def check_client_id_url(url: str):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname:
        raise CIMDError('client_id must be an https URL')
    if not parts.path or parts.path == '/':
        raise CIMDError('client_id URL must have a path')
    if '@' in parts.netloc or '#' in url:
        raise CIMDError('client_id URL must not contain credentials or a fragment')
    if any(seg in ('.', '..') for seg in parts.path.split('/')):
        raise CIMDError('client_id URL must not contain dot segments')


def resolve_public(host: str, port: int) -> str:
    """The address to connect to, if every address the host resolves to is public"""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise CIMDError(f'cannot resolve {host}') from e
    addresses = [info[4][0] for info in infos]
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise CIMDError(f'{host} does not resolve to a public address')
    return addresses[0]


def fetch(url: str) -> tuple[int, urllib3.HTTPHeaderDict, bytes]:
    parts = urlsplit(url)
    port = parts.port or 443
    address = resolve_public(parts.hostname, port)
    pool = urllib3.HTTPSConnectionPool(address, port, server_hostname=parts.hostname,
                                       assert_hostname=parts.hostname, timeout=CIMD_TIMEOUT, retries=False)
    path = parts.path + (f'?{parts.query}' if parts.query else '')
    user_agent = config.get('auth.oauth2.cimd.user_agent', 'Allura-OAuth/1.0')
    try:
        resp = pool.urlopen('GET', path, redirect=False, preload_content=False,
                            headers={'Host': parts.netloc, 'Accept': 'application/json', 'User-Agent': user_agent})
        try:
            body = resp.read(CIMD_MAX_BYTES + 1)
        finally:
            resp.release_conn()
    except urllib3.exceptions.HTTPError as e:
        raise CIMDError(f'could not fetch the client document: {type(e).__name__}') from e
    finally:
        pool.close()
    return resp.status, resp.headers, body


def ttl(headers) -> int:
    cache_control = headers.get('cache-control', '')
    if 'no-store' in cache_control or 'no-cache' in cache_control:
        return CIMD_MIN_TTL
    m = re.search(r'max-age=(\d+)', cache_control)
    if not m:
        return CIMD_DEFAULT_TTL
    return min(max(int(m.group(1)), CIMD_MIN_TTL), CIMD_MAX_TTL)


def parse_document(url: str, status: int, body: bytes) -> dict:
    if status != 200:
        raise CIMDError(f'the client document returned HTTP {status}')
    if len(body) > CIMD_MAX_BYTES:
        raise CIMDError('the client document is too large')
    try:
        doc = json.loads(body)
    except ValueError as e:
        raise CIMDError('the client document is not JSON') from e
    if not isinstance(doc, dict):
        raise CIMDError('the client document is not a JSON object')
    if doc.get('client_id') != url:
        raise CIMDError('the client document does not name this client_id')
    # a client may prefer another method, as long as it also lists none
    methods = doc.get('token_endpoint_auth_methods_supported')
    public = doc.get('token_endpoint_auth_method') == 'none' or (isinstance(methods, list) and 'none' in methods)
    if 'client_secret' in doc or not public:
        raise CIMDError('the client document must allow a public client (token_endpoint_auth_method "none")')

    name = doc.get('client_name')
    if not isinstance(name, str) or not name.strip():
        raise CIMDError('the client document has no client_name')
    redirect_uris = doc.get('redirect_uris')
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise CIMDError('the client document has no redirect_uris')
    allowed = [u for u in redirect_uris if isinstance(u, str) and https_or_loopback(u)][:MAX_REDIRECT_URIS]
    if not allowed:
        raise CIMDError('none of the client document redirect_uris is https or loopback')
    # grants we don't support (jwt-bearer, device_code) are ignored; only the code flow matters
    if 'authorization_code' not in (doc.get('grant_types') or ['authorization_code']):
        raise CIMDError('the client document does not use the authorization_code grant')
    if 'code' not in (doc.get('response_types') or ['code']):
        raise CIMDError('the client document does not use the code response type')
    return {'name': name.strip()[:MAX_NAME_LEN], 'redirect_uris': allowed}


def ensure_cimd_client(client_id: str, scopes: list[str]) -> M.OAuth2ClientApp:
    """The client for a metadata-document client_id, fetched if missing or stale.  One per client product, not per
    connection; `scopes` is the most it may be granted"""
    check_client_id_url(client_id)
    cached = M.OAuth2ClientMetadataFetch.query.get(_id=client_id)
    if cached and cached.expires > datetime.utcnow():
        client = M.OAuth2ClientApp.query.get(client_id=client_id)
        if client:
            return client

    started = time.monotonic()
    try:
        status, headers, body = fetch(client_id)
        meta = parse_document(client_id, status, body)
    except CIMDError as e:
        log.warning('oauth2 cimd: %s rejected: %s (%dms)', client_id, e, (time.monotonic() - started) * 1000)
        raise

    client = M.OAuth2ClientApp.query.find_one_and_update(
        {'client_id': client_id},
        {'$set': {'name': meta['name'], 'redirect_uris': meta['redirect_uris'],
                  'description': 'Client ID Metadata Document: ' + client_id, 'scopes': scopes, 'user_id': None,
                  'registration': 'cimd'},
         '$setOnInsert': {'client_secret': h.cryptographic_nonce(), 'grant_type': 'authorization_code',
                          'response_type': 'code'}},
        upsert=True, return_document=ReturnDocument.AFTER)
    M.OAuth2ClientMetadataFetch.query.find_one_and_update(
        {'_id': client_id},
        {'$set': {'expires': datetime.utcnow() + timedelta(seconds=ttl(headers))}},
        upsert=True)
    log.info('oauth2 cimd: fetched %s as %r (%dms)', client_id, meta['name'], (time.monotonic() - started) * 1000)
    return client
