import logging
import re

from pylons import c

from ming.orm import ThreadLocalORMSession

from allura import model as M
from allura.lib import utils
from forgewiki import model as WM
from forgewiki.wiki_main import ForgeWikiApp

log = logging.getLogger(__name__)

default_description = r'^\s*(?:You can edit this description in the admin page)?\s*$'

default_personal_project_tmpl = ("This is the personal project of %s."
            " This project is created automatically during user registration"
            " as an easy place to store personal data that doesn't need its own"
            " project such as cloned repositories.\n\n%s")

def main():
    users = M.Neighborhood.query.get(name='Users')
    for chunk in utils.chunked_find(M.Project, {'neighborhood_id': users._id}):
        for p in chunk:
            user = p.user_project_of
            if not user:
                continue

            description = p.description
            if description is None or re.match(default_description, description):
                continue

            app = p.app_instance('wiki')
            if app is None:
                p.install_app('wiki')

            page = WM.Page.query.get(app_config_id=app.config._id, title='Home')
            if page is None:
                continue

            c.app = app
            c.project = p
            c.user = user

            if "This is the personal project of" in page.text:
                if description not in page.text:
                    page.text = "%s\n\n%s" % (page.text, description)
                    log.info("Update wiki home page text for %s" % user.username)
            elif "This is the default page" in page.text:
                page.text = default_personal_project_tmpl % (user.display_name, description)
                log.info("Update wiki home page text for %s" % user.username)
            else:
                pass

        ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
