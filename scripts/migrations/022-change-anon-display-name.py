from ming.orm.ormsession import ThreadLocalORMSession
from allura import model as M

def main():
    u = M.User.query.get(username='*anonymous')
    u.display_name = 'Anonymous'

    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

if __name__ == '__main__':
    main()