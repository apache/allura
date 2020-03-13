from forgeimporters.base import ToolImporter

from allura import model as M   


class AlluraImporter(ToolImporter):


    def get_user(self, username):
        if username is None:
            return M.User.anonymous()
        user = M.User.by_username(username)
        if not user:
            user = M.User.anonymous()
        return user

    def annotate(self, text, user, username, label=''):
        if  username != "" \
            and username != None \
            and user != None \
            and user.is_anonymous() \
            and username != 'nobody' \
            and username != '*anonymous':
            return '*Originally%s by:* %s\n\n%s' % (label, username, text)

        if text == None:
            text = ""

        return text


