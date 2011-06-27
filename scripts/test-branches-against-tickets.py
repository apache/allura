from ConfigParser import ConfigParser, NoOptionError
import json
import oauth2 as oauth
import os
import re
import shlex
import subprocess
import sys
import urlparse
import webbrowser

CP = ConfigParser()
re_ticket_branch = re.compile('^\s*origin/.*/(\d+)$')


def main():
    git('remote prune origin')

    branches_for_tickets = dict() # maps ticket numbers to the actual branch e.g., int(42) -> 'origin/rc/42'
    ticket_nums = dict() # maps ticket numbers to 'merged' or 'unmerged' according to the matching branch

    merged_branches = [ branch[2:] for branch in git('branch -r --merged dev') if re_ticket_branch.match(branch) ]
    unmerged_branches = [ branch[2:] for branch in git('branch -r --no-merged dev') if re_ticket_branch.match(branch) ]

    for branch in merged_branches:
        tn = int(re_ticket_branch.match(branch).group(1))
        branches_for_tickets[tn] = branch
        ticket_nums[tn] = 'merged'

    for branch in unmerged_branches:
        # we'll consider it merged if `git cherry` thinks it is
        commits = ''.join(git('cherry', 'dev', branch, strip_eol=False))
        tn = int(re_ticket_branch.match(branch).group(1))
        branches_for_tickets[tn] = branch
        ticket_nums[tn] = 'merged' if commits.find('+')==-1 else 'unmerged'

    failure = False

    CP.read(os.path.join(os.environ['HOME'], '.forgepushrc'))
    oauth_client = make_oauth_client()

    for tn in ticket_nums:
        resp = oauth_client.request('http://sourceforge.net/rest/p/allura/tickets/%s/' % tn)
        #assert resp[0]['status'] == '200', (resp, tn)
        if resp[0]['status'] != '200':
            continue
        ticket = json.loads(resp[1])['ticket']
        if ticket is None:
            continue
        is_closed = ticket['status'] in ('closed', 'validation')
        is_merged = ticket_nums[tn] == 'merged'

        if is_closed != is_merged:
            print('<http://sourceforge.net/p/allura/tickets/%s/> is status:"%s", but the branch "%s" is %s' % (tn, ticket['status'], branches_for_tickets[tn], ticket_nums[tn]))
            failure = True

        if failure:
            sys.exit(1)


def make_oauth_client():
    """
    Build an oauth.Client with which callers can query Allura.
    See format_changes for an example use.

    Uses global CP, a ConfigParser

    Re-usable - copy & pasted between Allura, sfpy, and sfx push scripts
    """

    # https://sourceforge.net/p/forge/documentation/API%20-%20Beta/
    REQUEST_TOKEN_URL = 'http://sourceforge.net/rest/oauth/request_token'
    AUTHORIZE_URL = 'https://sourceforge.net/rest/oauth/authorize'
    ACCESS_TOKEN_URL = 'http://sourceforge.net/rest/oauth/access_token'
    oauth_key = option('re', 'oauth_key', 'Forge API OAuth Key (https://sourceforge.net/auth/oauth/): ')
    oauth_secret = option('re', 'oauth_secret', 'Forge API Oauth Secret: ')
    consumer = oauth.Consumer(oauth_key, oauth_secret)

    try:
        oauth_token = CP.get('re', 'oauth_token')
        oauth_token_secret = CP.get('re', 'oauth_token_secret')
    except NoOptionError:
        client = oauth.Client(consumer)
        resp, content = client.request(REQUEST_TOKEN_URL, 'GET')
        assert resp['status'] == '200', resp

        request_token = dict(urlparse.parse_qsl(content))
        pin_url = "%s?oauth_token=%s" % (AUTHORIZE_URL, request_token['oauth_token'])
        if getattr(webbrowser.get(), 'name', '') == 'links':
            # sandboxes
            print("Go to %s" % pin_url)
        else:
            webbrowser.open(pin_url)
        oauth_verifier = raw_input('What is the PIN? ')

        token = oauth.Token(request_token['oauth_token'], request_token['oauth_token_secret'])
        token.set_verifier(oauth_verifier)
        client = oauth.Client(consumer, token)
        resp, content = client.request(ACCESS_TOKEN_URL, "GET")
        access_token = dict(urlparse.parse_qsl(content))
        oauth_token = access_token['oauth_token']
        oauth_token_secret = access_token['oauth_token_secret']

        CP.set('re', 'oauth_token', oauth_token)
        CP.set('re', 'oauth_token_secret', oauth_token_secret)

    access_token = oauth.Token(oauth_token, oauth_token_secret)
    return oauth.Client(consumer, access_token)


def git(*args, **kw):
    if len(args)==1 and isinstance(args[0], basestring):
        argv = shlex.split(args[0])
    else:
        argv = list(args)
    if argv[0] != 'git':
        argv.insert(0, 'git')
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p.wait()
    output = p.stdout.readlines()
    if kw.get('strip_eol', True):
        output = [ line.rstrip('\n') for line in output ]
    return output


def option(section, key, prompt=None):
    """ shared (copy/paste) between Allura & sfpy """
    if not CP.has_section(section):
        CP.add_section(section)
    if CP.has_option(section, key):
        value = CP.get(section, key)
    else:
        value = raw_input(prompt or ('%s: ' % key))
        CP.set(section, key, value)
    return value


if __name__ == '__main__':
    main()
