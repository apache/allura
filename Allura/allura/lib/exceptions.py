class ForgeError(Exception): pass
class ProjectConflict(ForgeError): pass
class ToolError(ForgeError): pass
class NoSuchProjectError(ForgeError): pass
class MailError(ForgeError): pass
class AddressException(MailError): pass

class CompoundError(ForgeError):
    def __repr__(self):
        return '<%s>\n%s\n</%s>'  % (
            self.__class__.__name__,
            '\n'.join(map(repr, self.args)),
            self.__class__.__name__)
