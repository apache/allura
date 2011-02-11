import os
import re
import readline # changes raw_input to allow line editing (sorry, pyflakes)
import shlex
import string
import subprocess
import sys
from collections import defaultdict
from ConfigParser import ConfigParser
from datetime import date
from urlparse import urljoin
from optparse import OptionParser

from allura.lib import rest_api

VERBOSE = 2
DRY_RUN = False
CP = ConfigParser()

re_ticket_ref = re.compile(r'\[#(\d+)\]')
re_allura_ref = re.compile(r'\nreference: ')
re_git_dir = re.compile(r'.*\.git/?\Z')
re_ws = re.compile(r'\s')

CRED={}

def main():
    global DRY_RUN, VERBOSE
    op = OptionParser()
    op.add_option('--dry-run', action='store_true', dest='dry_run', default=False)
    (options, args) = op.parse_args(sys.argv[1:])
    if options.dry_run:
        DRY_RUN = True
        print("This is a dry-run: tags will be created locally but nothing will be pushed.")

    CP.read(os.path.join(os.environ['HOME'], '.forgepushrc'))
    engineer = option('re', 'engineer', 'Name of engineer pushing: ')
    sf_identity = option('re', 'sf_identity', 'Your SourceForge.net user-name: ')
    api_key = option('re', 'api_key', 'Forge API Key:')
    secret_key = option('re', 'secret_key', 'Forge Secret Key:')
    classic_path = option('re', 'classic_path', 'The path to your forge-classic repo:')
    theme_path = option('re', 'theme_path', 'The path to your sftheme repo:')
    if not re_git_dir.match(classic_path):
        classic_path += '/.git/'
    if not re_git_dir.match(theme_path):
        theme_path += '/.git/'
    CRED['api_key'] = api_key
    CRED['secret_key'] = secret_key

    if ask_yes_or_no('Confirm each git command?', 'y'):
        VERBOSE = 2
    elif ask_yes_or_no('Echo each git command?', 'y'):
        VERBOSE = 1
    else:
        VERBOSE = 0

    if VERBOSE:
        print("Making sure our existing tags are up-to-date...")
    git('fetch origin --tags')
    git('fetch origin --tags', git_dir=classic_path)
    git('fetch origin --tags', git_dir=theme_path)
    text, new_tag = make_ticket_text(engineer, classic_path, theme_path)
    raw_input("Make sure you merged dev up into master for forge, forge_classic, and sftheme.")
    raw_input("Make sure there are no new dependencies, or RPM's are built for all dependencies.")
    raw_input("Make sure a new sandbox builds and starts without engr help.")
    print('*** Create a ticket on SourceForge (https://sourceforge.net/p/allura/tickets/new/) with the following contents:')
    print('*** Summary: Production Push (R:%s, D:%s) - allura' % (
        new_tag, date.today().strftime('%Y%m%d')))
    print('---BEGIN---')
    print(text)
    print('---END---')
    newforge_num = raw_input('What is the newforge ticket number? ')
    print('*** Create a SOG Trac ticket (https://control.sog.geek.net/sog/trac/newticket?keywords=LIAISON) with the same summary...')
    print('---BEGIN---')
    sog_text = re_ticket_ref.sub('FO:\g<1>', text)
    print(re_allura_ref.sub('\nreference: https://sourceforge.net/p/allura/tickets/%s/' % newforge_num, sog_text))
    print('---END---')
    sog_num = raw_input('What is the SOG ticket number? ')
    raw_input('Now link the two tickets.')
    if VERBOSE:
        print("Ask for approval (copy/paste the following text into Jabber)")
    raw_input('Allura push, %s, for your approval (https://control.sog.geek.net/sog/trac/ticket/%s).' % (new_tag, sog_num))

    if VERBOSE:
        print("Tag and push the Allura repo for release...")
    tag_message = '[#%s] - Push to RE' % newforge_num
    git('tag', '-a', '-m', tag_message, new_tag, 'master')
    git('push', 'origin', 'master', new_tag)
    git('push', 'control.sog.geek.net:allura-live', 'master', new_tag)
    if ask_yes_or_no('Do you want to push to the public repo, too?', 'n'):
        git('push', 'ssh://%s@git.code.sf.net/p/allura/git.git' % sf_identity, 'master', new_tag, fail_ok=True)

    if VERBOSE:
        print("Tag and push the forge-classic repo for release...")
    git('tag', '-a', '-m', tag_message, new_tag, 'master', git_dir=classic_path)
    git('push', 'origin', 'master', new_tag, git_dir=classic_path)
    git('push', 'control.sog.geek.net:forge-classic-live', 'master', new_tag, git_dir=classic_path)

    if VERBOSE:
        print("Tag and push the sftheme repo for release...")
    git('tag', '-a', '-m', tag_message, new_tag, 'master', git_dir=theme_path)
    git('push', 'origin', 'master', new_tag, git_dir=theme_path)
    git('push', 'control.sog.geek.net:sftheme-live', 'master', new_tag, git_dir=theme_path)

    if VERBOSE:
        print("Tell SOG we're ready (copy/paste the following text into Jabber)")
    print('Allura release %s is ready for pushing (https://control.sog.geek.net/sog/trac/ticket/%s).' % (new_tag, sog_num))
    CP.write(open(os.path.join(os.environ['HOME'], '.forgepushrc'), 'w'))
    if VERBOSE:
        print("That's all, folks!")

def make_ticket_text(engineer, classic_path, theme_path):
    tag_prefix = date.today().strftime('allura_%Y%m%d')
    # get release tag
    existing_tags_today = git('tag -l %s*' % tag_prefix)
    if existing_tags_today:
        new_tag = '%s.%.2d' % (tag_prefix, len(existing_tags_today))
    else:
        new_tag = tag_prefix
    since_last_release = get_last_release_tag() + '..master'
    format = '--format=* %h %s'
    if VERBOSE:
        print("Examining commits to build the list of fixed tickets...")
    changes = git('log', format, since_last_release, strip_eol=False)
    changes += git('log', format, since_last_release, git_dir=classic_path, strip_eol=False)
    changes += git('log', format, since_last_release, git_dir=theme_path, strip_eol=False)
    if not changes:
        print('There were no commits found; maybe you forgot to merge dev->master? (Ctrl-C to abort)')
    changelog = ''.join(changes or [])
    changes = ''.join(format_changes(changes))
    print('Changelog:\n%s' % changelog)
    print('Tickets:\n%s' % changes)
    prelaunch = []
    postlaunch = []
    if ask_yes_or_no('Does this release require a migration?', 'y'):
        prelaunch.append('* dump the database in case we need to roll back')
        postlaunch.append('* allurapaste flyway --url mongo://sfn-mongo:27017/')
    if ask_yes_or_no('Does this release require ensure_index?', 'y'):
        postlaunch.append('* allurapaste ensure_index /var/local/config/production.ini')
    if postlaunch:
        postlaunch = [ 'From sfu-scmprocess-1 do the following:\n' ] + postlaunch
        postlaunch = '\n'.join(postlaunch)
    else:
        postlaunch = '-none-'
    if prelaunch:
        prelaunch = [ 'From sfn-mongo do the following:\n' ] + prelaunch
        prelaunch = '\n'.join(prelaunch)
    else:
        prelaunch = '-none-'
    return TICKET_TEMPLATE.substitute(locals()), new_tag

def format_changes(changes):
    if not changes:
        yield '-none-'
    ticket_groups = defaultdict(list)
    for change in changes:
        for m in re_ticket_ref.finditer(change):
            ticket_groups[m.group(0)].append(change)
    try:
        cli = rest_api.RestClient(
            base_uri='http://sourceforge.net', **CRED)
        for ref, commits in sorted(ticket_groups.iteritems()):
            ticket_num = ref[2:-1]
            ticket = cli.request(
                'GET',
                urljoin('/rest/p/allura/tickets/', str(ticket_num)) + '/')['ticket']
            if ticket is None: continue
            verb = {
                'validation': 'Fix',
                'closed': 'Fix' }.get(ticket['status'], 'Address')
            yield ' * %s %s: %s\n' % (verb, ref, ticket['summary'])
    except:
        print('*** ERROR CONTACTING FORGE FOR TICKET SUMMARIES ***')
        raise
        for ci in changes:
            yield ci

def ask_yes_or_no(prompt, default):
    result = raw_input('%s [%s] ' % (prompt, default)) or default
    return result[:1].lower() in ('y', '1')

def assemble_command(*args):
    quoted = [ "'%s'" % arg if re_ws.search(arg) else arg for arg in args ]
    return ' '.join(quoted)

def git(*args, **kwargs):
    if len(args)==1 and isinstance(args[0], basestring):
        argv = shlex.split(args[0])
    else:
        argv = list(args)
    if argv[0] != 'git':
        argv.insert(0, 'git')
    if DRY_RUN and argv[1]=='push':
        argv.insert(2, '--dry-run')
    if 'git_dir' in kwargs:
        argv.insert(1, '--git-dir=%s' % kwargs['git_dir'])
    full_command = assemble_command(*argv)
    if VERBOSE==2:
        raw_input(full_command)
    elif VERBOSE==1:
        print(full_command)
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    rc = p.wait()
    output = p.stdout.readlines()
    if kwargs.get('strip_eol', True):
        output = [ line[:-1] for line in output ]
    if rc:
        print('Error: %s' % full_command)
        for line in output: print(line.rstrip())
        if not kwargs.get('fail_ok', False):
            import pdb; pdb.set_trace()
    return output

def get_last_release_tag():
    has_clear_history = getattr(readline, 'clear_history')
    if has_clear_history:
        readline.clear_history()
    for rtag in git('tag -l release_*'):
        readline.add_history(rtag)
    for atag in git('tag -l allura_*'):
        readline.add_history(atag)
    default = atag or rtag or ''
    result = raw_input('Last successful push? [%s] ' % default) or default
    if has_clear_history:
        readline.clear_history()
    return result

def option(section, key, prompt=None):
    if not CP.has_section(section):
        CP.add_section(section)
    if CP.has_option(section, key):
        value = CP.get(section, key)
    else:
        value = raw_input(prompt or ('%s: ' % key))
        CP.set(section, key, value)
    return value

TICKET_TEMPLATE=string.Template('''{{{
#!push

(engr) Name of Engineer pushing: $engineer
(engr) Which code tree(s): allura, forge-classic, sftheme
(engr) Is configtree to be pushed?: no
(engr) Which release/revision is going to be synced?: $new_tag
(engr) Itemized list of changes to be launched with sync:

$changes

Pre-launch dependencies:

$prelaunch

Post-launch dependencies:

$postlaunch

(engr) Approved for release (Dean/Dave/John): None
(sog) Outcome of sync:

reference: 
}}}''')

if __name__ == '__main__':
    main()
