import os
import string

HOME=os.environ['HOME']

USERS=['user%.2d' % i for i in range(1, 21) ]
USERS += [
    'admin1', 'admin2',
    'dovethunder', 'dovetail', 'dovestream', 'dovetree', 'dovespangle',
    'dovemeade', 'dovestar', 'dovebuyer', 'dovesomething', 'dovesweet', 'dovewood' ]
SSH_CONFIG = '%s/.ssh/config' % HOME
LDIF_FILE = '%s/users.ldif' % HOME
KEYFILE='%s/.ssh/allura_rsa' % HOME

def main():

    # Generate ssh key for SCM login
    os.system('cp %s %s.bak' % (SSH_CONFIG, SSH_CONFIG))
    with open(SSH_CONFIG) as fp:
        lines = fp.readlines()
    new_lines = [
        SSH_TMPL.substitute(
            sb_host=sb_host,
            sb=sb,
            veid='%d0%.2d' % (sb_host, sb))
        for sb_host in 5,6,7,9
        for sb in range(99) ]
    new_lines = '\n'.join(new_lines)
    found_star = False
    with open(SSH_CONFIG, 'w') as fp:
        for line in lines:
            if not found_star and line.startswith('Host *'):
                print >> fp, new_lines
                found_star = True
            print >> fp, line.rstrip()
        if not found_star:
            print >> fp, new_lines
    os.system("ssh-keygen -t rsa -b 2048 -N '' -f %s" % KEYFILE)

    # Generate ldif
    pubkey = open(KEYFILE + '.pub').read()
    with open(LDIF_FILE, 'w') as fp:
        for user in USERS:
            print >> fp, LDIF_TMPL.substitute(
                user=user, pubkey=pubkey)

    # Update LDAP
    assert 0 == os.system('/usr/local/sbin/ldaptool modify -v -f %s' % LDIF_FILE)

SSH_TMPL=string.Template('''
Host svn*-$veid svn*-${veid}.sb.sf.net
  Hostname 10.58.${sb_host}.${sb}
  Port 16
  IdentityFile ~/.ssh/allura_rsa

Host git*-$veid git*-${veid}.sb.sf.net
  Hostname 10.58.${sb_host}.${sb}
  Port 23
  IdentityFile ~/.ssh/allura_rsa
''')

LDIF_TMPL=string.Template('''
dn: cn=$user,ou=users,dc=sf,dc=net
changetype: modify
add: sshPublicKey
sshPublicKey: $pubkey
''')

if __name__ == '__main__':
    main()
