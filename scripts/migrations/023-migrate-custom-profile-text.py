import logging

from pylons import c

from ming.orm import ThreadLocalORMSession

from allura import model as M
from forgewiki import model as WM
from forgewiki.wiki_main import ForgeWikiApp

log = logging.getLogger(__name__)

default_description = u'You can edit this description in the admin page'

default_personal_project_tmpl = ("This is the personal project of %s."
            " This project is created automatically during user registration"
            " as an easy place to store personal data that doesn't need its own"
            " project such as cloned repositories.\n%s")

def main():
    for p in M.Project.query.find().all():
        user = p.private_project_of()
        if not user:
            continue

        app = p.app_instance('wiki')
        if app is None:
            p.install_app('wiki')

        c.app = app
        c.project = p
        c.user = user

        page = WM.Page.query.get(app_config_id=c.app.config._id, title='Home')
        if page is None:
            c.app.install(p)
            page = WM.Page.query.get(app_config_id=c.app.config._id, title='Home')
            if page is None:
                log.info("Can't add page for %s home project" % user.username)
                continue

        description = p.description
        if description is None or description == "":
            description = default_description

        if "This is the personal project of" in page.text:
            if description not in page.text:
                page.text = "%s\n%s" % (page.text, description)
        elif "This is the default page" in page.text:
            page.text = default_personal_project_tmpl % (user.username, description)
        else:
            pass

        log.info("Update wiki home page text for %s" % user.username)

    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
