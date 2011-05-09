import logging
from getpass import getpass
from optparse import OptionParser

from suds.client import Client
from suds import WebFault

log = logging.getLogger(__file__)

'''

http://help.collab.net/index.jsp?topic=/teamforge520/reference/api-services.html

http://www.open.collab.net/nonav/community/cif/csfe/50/javadoc/index.html?com/collabnet/ce/soap50/webservices/page/package-summary.html

'''


def main():
    optparser = OptionParser(usage='''%prog [options]''')
    optparser.add_option('--api-url', dest='api_url', help='e.g. https://hostname/ce-soap50/services/')
    optparser.add_option('-u', '--username', dest='username')
    optparser.add_option('-p', '--password', dest='password')
    options, args = optparser.parse_args()


    c = Client(options.api_url + 'CollabNet?wsdl', location=options.api_url + 'CollabNet')
    api_v = c.service.getApiVersion()
    if not api_v.startswith('5.4.'):
        log.warning('Unexpected API Version %s.  May not work correctly.' % api_v)


    s = c.service.login(options.username, options.password or getpass('Password: '))
    teamforge_v = c.service.getVersion(s)
    if not teamforge_v.startswith('5.4.'):
        log.warning('Unexpected TeamForge Version %s.  May not work correctly.' % teamforge_v)


    discussion = Client(options.api_url + 'DiscussionApp?wsdl', location=options.api_url + 'DiscussionApp')
    news = Client(options.api_url + 'NewsApp?wsdl', location=options.api_url + 'NewsApp')

    projects = c.service.getProjectList(s)
    for p in projects[0]:
        print p
        print c.service.getProjectData(s, p.id)
        print c.service.getProjectAccessLevel(s, p.id)
        print c.service.listProjectAdmins(s, p.id)

        for forum in discussion.service.getForumList(s, p.id)[0]:
            print forum.title
            for topic in discussion.service.getTopicList(s, forum.id)[0]:
                print '  ', topic.title
                for post in discussion.service.getPostList(s, topic.id)[0]:
                    print '    ', post.title, post.createdDate, post.createdByUserName
                    print post.content
                    print
                    break
                break
            break

        print news.service.getNewsPostList(s, p.id)
        break

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARN)
    main()
