import re

from allura import model as M


def main():
    categories_regex = '|'.join([
        'Translations',
        'Programming Language',
        'User Interface',
        'Database Environment',
        'Operating System',
        'Topic',
    ])
    M.TroveCategory.query.update(
        {'fullname': re.compile(r'^(%s)' % categories_regex)},
        {'$set': {'show_as_skill': True}},
        multi=True)

if __name__ == '__main__':
    main()
